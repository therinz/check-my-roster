import re

from datetime import timedelta
from bs4 import BeautifulSoup

from datastructures import DutyDay, Flight, OtherDuty
from helpers import get_rostercodes, time_diff


class ConvertDutyDay:
    """ Read list of items on day of roster and return DutyDay with each Duty item.

    :param self.lv: Store local values for working on roster decryption
    :type self.lv: dict
    :return: DutyDay class containing list of Flight
            and/or OtherDuty and optional report & end times
    """
    roster_codes = get_rostercodes()
    timed_roster_codes = [code for code, values in roster_codes.items()
                          if values[0] == "True"]
    ground_pos_codes = ["OWN", "TAXI", "TRN", "NSO"]

    def __init__(self):
        self.lv = {}
        self.duties, self.days = [], []

    def search_duty_type(self, row):
        search_flight_number = re.search(r"[0-9]{3,4}", row)
        search_non_flight = re.search(r"[A-Z/]{3,4}", row)
        if row in ConvertDutyDay.ground_pos_codes:
            # Takes into account taxi between bases.
            self.lv["position"] = "ground"
            self.lv["flight_number"] = True
        elif search_flight_number:
            self.lv["flight_number"] = search_flight_number.group()
            if row[-1] == "R" or row[-1] == "A":
                self.lv["comeback"] = row[-1]
            if self.lv.get("end_time"):
                self.clean_up()
        elif search_non_flight and not self.lv.get("flight_number"):
            self.lv["other_duty"] = search_non_flight.group()
            if self.lv["other_duty"] not in ConvertDutyDay.timed_roster_codes:
                self.lv["no_time"] = True

    def time_details(self, search_time, prev):
        time_type = None
        if self.lv.get("flight_number"):
            if not self.lv.get("report_time"):
                time_type = "report_time"
            elif prev == "report_time":
                time_type = "STD"
            elif prev == "STD":
                time_type = "STA"
        elif self.lv.get("other_duty"):
            if prev == "start_time":
                time_type = "end_time"
            else:
                time_type = "start_time"
        elif self.lv.get("last_time_type") == "end_time":
            # flight after stby
            time_type = "report_time"
        else:
            # could be after flight or flight-stby
            time_type = "off_time"
        self.lv[time_type] = search_time
        self.lv["previous_item"] = time_type

    def flight_details(self, row, search_iata):
        if self.lv.get("position") != "ground" and re.search(r"\*", row):
            self.lv["position"] = "air"
        if not self.lv.get("dep"):
            self.lv["dep"] = search_iata.group()
        else:
            self.lv["arr"] = search_iata.group()

    def clean_up(self, end_of_duty=False, keep_duty_type=False):
        save_vals = {}
        if end_of_duty:
            self.days.append(DutyDay(self.duties,
                                     report_time=self.lv.get("report_time"),
                                     off_duty=self.lv.get("off_time")))
            self.duties = []
            if keep_duty_type:
                # After clearing lv, new info will be lost, so save before
                save_vals.update({"flight_number": self.lv.get("flight_number"),
                                  "other_duty": self.lv.get("other_duty")})
        else:
            report = self.lv.get("report_time")
            if report:
                save_vals.update({"report_time": report,
                                  "previous_item": "report_time"})
            previous = self.lv.get("previous_item")
            no_time = self.lv.get("no_time")
            if previous:
                # If last time > 9h end previous duty day
                save_vals.update({"last_time": self.lv[previous],
                                  "last_type": previous})
            elif no_time:
                save_vals.update({"last_type": "no_time"})
        self.lv.clear()
        self.lv.update(save_vals)

    def process(self, day):
        i = 0
        for j, row in enumerate(day):
            skip_vals = ["None", " EJU", " ", "Block", "Duty", " OWNA", "(320)", "(321)", "EZS", " EZS"]
            if j > (len(day) - 4):
                # compensate for block & duty times at end of day
                break
            elif row in skip_vals or len(row) < 3:
                i += 1
                if i > 3:
                    if len(self.duties) > 0 and self.lv.get("last_type") == "no_time":
                        self.clean_up(end_of_duty=True)
                    break
                continue
            i = 0
            self.search_duty_type(row)
            search_time = re.search(r"[0-9]{2}:[0-9]{2}", row)
            if search_time:
                previous = self.lv.get("previous_item")
                time = search_time.group()
                unfinished = (self.lv.get("last_type") == "off_time"
                              or self.lv.get("last_type") == "end_time")
                if (unfinished and (time_diff(self.lv.get("last_time"), time)
                                    > timedelta(hours=9))):
                    self.clean_up(end_of_duty=True, keep_duty_type=True)
                self.time_details(time, previous)
            elif self.lv.get("flight_number") and row not in ConvertDutyDay.ground_pos_codes:
                search_iata = re.search(r"[A-Z]{3}\Z", row)
                if search_iata:
                    self.flight_details(row, search_iata)
                    continue
            # Now when ready save found values in duties
            prev = self.lv.get("previous_item")
            if prev == "STA":
                # With STA all flight details are known. Save as Flight in duties dict.
                self.duties.append(Flight(self.lv["flight_number"],
                                          self.lv["dep"], self.lv["arr"],
                                          self.lv["STD"], self.lv["STA"],
                                          position=self.lv.get("position"),
                                          comeback=self.lv.get("comeback")))
                self.clean_up()
            elif prev == "end_time" or self.lv.get("no_time"):
                # Some non-flights have start and end times, others don't. Save as OtherDuty in duties dict.
                self.duties.append(OtherDuty(self.lv["other_duty"],
                                             start_time=self.lv.get("start_time"),
                                             end_time=self.lv.get("end_time")))
                self.clean_up()
            if self.lv.get("off_time"):
                self.clean_up(end_of_duty=True)

    def day_for_day(self, month):
        for day in month:
            self.process(day)
        if len(self.duties) > 0:
            self.clean_up(end_of_duty=True)


class ReadRoster:
    """ Open and read html roster. """

    def __init__(self, source):
        self.source = source
        try:
            with open(self.source) as html:
                self.soup = BeautifulSoup(html.read(), "html.parser")
        except FileNotFoundError as file_error:
            print(file_error)
        else:
            self.print_roster()

    def read_workdays(self):
        """ Find every line in html roster with duty element.

        :return: Nested list with rows per column.
        """
        rows = []
        for row in self.soup.find_all("tr"):
            cells = [str(cell.string) for cell in row.find_all("td")]
            if len(cells) == 32:
                rows.append(cells)
        return [[row[i] for row in rows] for i in range(32)]

    def night_stops(self):
        search_hotel = self.soup.find(string=re.compile(r"[A-Za-z]{6,12} HOTEL"))
        if search_hotel is not None:
            return re.findall(r"[A-Z][a-z]{2}[0-9]{2}", str(search_hotel.parent))

    def print_roster(self):
        nominal = {"s": 8, "m": 12, "l": 15, "xl": 25}
        total = num_flights = positioning = asby = ground_duties = domestic = days_flying = days_at_work = 0
        off_duty = {"LVE": 0, "SICK": 0, "ULV": 0}
        roster_days = ConvertDutyDay()
        roster_days.day_for_day(self.read_workdays())
        for i, duty_day in enumerate(roster_days.days, 1):
            on_asby = multi_pos = multi_gd = at_work = False
            if duty_day is None:
                continue
            print(f"Day {i}")
            for duty in duty_day.duties:
                if isinstance(duty, Flight):
                    distance, sector = duty.distance()
                    if not at_work:
                        days_at_work += 1
                        days_flying += 1
                        at_work = True
                    if duty.position:
                        if (not multi_pos and
                                ((duty.dep not in Flight.simulators
                                  and duty.arr not in Flight.simulators)
                                 or distance > 15)):
                            # Length not taken into account, only 1 leg per day
                            # Ground pos to LGW and MXP not properly calculated
                            positioning += 1
                        multi_pos = True
                        print("    {} positioning duty from {} to {}"
                              .format(str(duty.position).capitalize(),
                                      duty.dep, duty.arr))
                    elif duty.comeback == "R":
                        print(f"    (This flight in {duty.dep} returned "
                              f"to stand while still on ground.)")
                    else:
                        total += nominal[sector]
                        num_flights += 1
                        icao_d = duty.airports_list[duty.dep].icao
                        icao_a = duty.airports_list[duty.arr].icao
                        if icao_d.startswith("LF") and icao_a.startswith("LF"):
                            domestic += 1
                        print(f"    Flight from {duty.dep} to {duty.arr}, "
                              f"length {distance} ({sector}).")
                        if on_asby:
                            asby -= 1
                            on_asby = False
                else:
                    roster_codes = get_rostercodes()
                    paid_codes = [code for code, values in roster_codes.items() if values[2] == "True"]
                    if duty.rostercode in paid_codes and not multi_gd:
                        if not at_work:
                            days_at_work += 1
                            at_work = True
                        ground_duties += 1
                        multi_gd = True
                    for item in off_duty.keys():
                        if duty.rostercode == item:
                            off_duty[item] += 1
                    if duty.rostercode == "ASBY" or duty.rostercode == "ADTY":
                        if not at_work:
                            days_at_work += 1
                            at_work = True
                        on_asby = True
                        if time_diff(duty.start_time, duty.end_time) < timedelta(hours=4):
                            asby += 1
                        else:
                            asby += 2
                    print(f"    Duty with code {duty.rostercode}")
        paid_items = {"nominal sector": (total / 10),
                      "number of flights": num_flights,
                      "French domestic flights": domestic,
                      "positioning duties": positioning,
                      "airport standby": asby,
                      "paid ground duties": ground_duties,
                      "days flying": days_flying,
                      "days incl asby & ground duties": days_at_work}
        paid_items.update(off_duty)
        for item, count in paid_items.items():
            if count > 0:
                print(f"Total {item} count is {count}.")
        night_stops = self.night_stops()
        if night_stops is not None:
            nights = ", ".join(night_stops)
            print("\nNightstopping {} times: {}".format(len(night_stops), nights))

    # def year_stats(self):
    #     nominal = {"s": 8, "m": 12, "l": 15, "xl": 25}
    #     total = num_flights = positioning = asby = ground_duties = domestic = 0
    #     off_duty = {"LVE": 0, "SICK": 0, "ULV": 0}
    #
    #     roster_days = ConvertDutyDay()
    #     roster_days.day_for_day(self.read_workdays())
    #     for i, duty_day in enumerate(roster_days.days, 1):
    #         on_asby = multi_pos = multi_gd = False
    #         if duty_day is None:
    #             continue
    #         print(f"Day {i}")
    #         for duty in duty_day.duties:
    #             if isinstance(duty, Flight):
    #                 distance, sector = duty.distance()
    #                 if duty.position:
    #                     if (not multi_pos and
    #                             ((duty.dep not in Flight.simulators
    #                               and duty.arr not in Flight.simulators)
    #                              or distance > 15)):
    #                         # Length not taken into account, only 1 leg per day
    #                         # Ground pos to LGW and MXP not properly calculated
    #                         positioning += 1
    #                     multi_pos = True
    #                     print("    {} positioning duty from {} to {}"
    #                           .format(str(duty.position).capitalize(),
    #                                   duty.dep, duty.arr))
    #                 elif duty.comeback == "R":
    #                     print(f"    (This flight in {duty.dep} returned "
    #                           f"to stand while still on ground.)")
    #                 else:
    #                     total += nominal[sector]
    #                     num_flights += 1
    #                     icao_d = duty.airports_list[duty.dep].icao
    #                     icao_a = duty.airports_list[duty.arr].icao
    #                     if icao_d.startswith("LF") and icao_a.startswith("LF"):
    #                         domestic += 1
    #                     print(f"    Flight from {duty.dep} to {duty.arr}, "
    #                           f"length {distance} ({sector}).")
    #                     if on_asby:
    #                         asby -= 1
    #                         on_asby = False
    #             else:
    #                 roster_codes = get_rostercodes()
    #                 paid_codes = [code for code, values in roster_codes.items() if values[2] == "True"]
    #                 if duty.rostercode in paid_codes and not multi_gd:
    #                     ground_duties += 1
    #                     multi_gd = True
    #                 for item in off_duty.keys():
    #                     if duty.rostercode == item:
    #                         off_duty[item] += 1
    #                 if duty.rostercode == "ASBY":
    #                     on_asby = True
    #                     if time_diff(duty.start_time, duty.end_time) < timedelta(hours=4):
    #                         asby += 1
    #                     else:
    #                         asby += 2
    #                 print(f"    Duty with code {duty.rostercode}")
    #     paid_items = {"nominal sector": (total / 10),
    #                   "number of flights": num_flights,
    #                   "French domestic flights": domestic,
    #                   "positioning duties": positioning,
    #                   "airport standby": asby,
    #                   "paid ground duties": ground_duties}
    #     paid_items.update(off_duty)
    #     for item, count in paid_items.items():
    #         if count > 0:
    #             print(f"Total {item} count is {count}.")
    #     night_stops = self.night_stops()
    #     if night_stops is not None:
    #         nights = ", ".join(night_stops)
    #         print("\nNightstopping {} times: {}".format(len(night_stops), nights))



import re

from datetime import timedelta
from bs4 import BeautifulSoup

from datastructures import DutyDay, Flight, OtherDuty, get_rostercodes
from datastructures import time_diff

GND_POS = ["OWN", "TAXI", "TRN", "NSO"]


class ParseRoster:
    """
    Read list of items on day of roster and return DutyDay with each Duty item.

    :param self.lv: Store local values for working on roster decryption
    :type self.lv: dict
    :return: DutyDay class containing list of Flight
            and/or OtherDuty and optional report & end times
    """
    roster_codes = get_rostercodes()
    timed_roster_codes = [code
                          for code, values in roster_codes.items()
                          if values[0] == "True"]

    def __init__(self):
        self.continued_duty = False
        self.lv = {}
        self.duties, self.days = [], []

    def search_duty_type(self, row):
        search_flight_number = re.search(r"[0-9]{3,4}", row)
        search_non_flight = re.search(r"[A-Z/]{3,4}", row)
        if row in GND_POS:
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
            if self.lv["other_duty"] not in ParseRoster.timed_roster_codes:
                self.lv["no_time"] = True

    def time_details(self, search_time, prev):
        """ Interpret current time type by switching after the previous. """

        switch = {"report_time": "STD",
                  "STD": "STA",
                  "start_time": "end_time"}
        # Flight in progress
        if self.lv.get("flight_number"):
            if not self.lv.get("report_time"):
                time_type = "report_time"
            else:
                time_type = switch.get(prev)
        # Timed duty other than a flight
        elif self.lv.get("other_duty"):
            time_type = switch.get(prev, "start_time")
        # Flight after stby
        elif self.lv.get("last_time_type") == "end_time":
            time_type = "report_time"
        # After flight or flight-stby
        else:
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
        """
        Delete values in dictionary cache. Method may be called on start of new
        day because previous day was unfinished, as set by keep_duty_type=True.

        """

        save_vals = {}

        # Duty has ended but isn't saved yet
        if end_of_duty:
            self.days.append(DutyDay(self.duties,
                                     report_time=self.lv.get("report_time"),
                                     off_duty=self.lv.get("off_time")))
            self.duties = []

            # Keep_duty_type signals new duty has already begun,
            # so save data from the new day.
            if keep_duty_type:
                save_vals.update({"flight_number": self.lv.get("flight_number"),
                                  "other_duty": self.lv.get("other_duty")})

        # Element of duty has finished, not the day completely
        else:
            report = self.lv.get("report_time")

            if report:
                save_vals.update({"report_time": report,
                                  "previous_item": "report_time"})
            previous = self.lv.get("previous_item")

            # If last time > 9h end previous duty day
            if previous:
                save_vals.update({"last_time": self.lv[previous],
                                  "last_type": previous})
            elif self.lv.get("no_time"):
                save_vals.update({"last_type": "no_time"})

        # Clear local values and save new data
        self.lv.clear()
        self.lv.update(save_vals)

    def day(self, day):
        """ For one day, loop through all rows and extract duties and times. """
        # TODO change get into "key in dict"
        i = 0
        for j, row in enumerate(day):
            skip_vals = ["None", " EJU", " ", "Block",
                         "Duty", " OWNA", "(320)", "(321)", "EZS", " EZS"]

            # Skip block & duty times at end of day
            if j > (len(day) - 4):
                break
            # Skip empty and non-relevant rows
            elif row in skip_vals or len(row) < 3:
                i += 1
                # More than 3 empty rows signals day off
                if i > 3:
                    # There may still be an unfinished duty from the day prior.
                    if (len(self.duties) > 0
                            and self.lv.get("last_type") == "no_time"):
                        self.clean_up(end_of_duty=True)
                    break
                continue
            i = 0

            # Check what's happening on row
            self.search_duty_type(row)
            search_time = re.search(r"[0-9]{2}:[0-9]{2}", row)

            # If current row is a time, check what type of activity
            if search_time:
                previous = self.lv.get("previous_item")
                time = search_time.group()
                unfinished = (self.lv.get("last_type") == "off_time"
                              or self.lv.get("last_type") == "end_time")
                if (unfinished and (time_diff(self.lv.get("last_time"), time)
                                    > timedelta(hours=9))):
                    # New day but still values in cache, so save that first.
                    self.clean_up(end_of_duty=True, keep_duty_type=True)
                self.time_details(time, previous)
            elif self.lv.get("flight_number") and row not in GND_POS:
                search_iata = re.search(r"[A-Z]{3}\Z", row)
                if search_iata:
                    self.flight_details(row, search_iata)
                    continue

            prev = self.lv.get("previous_item")
            # When STA is set, all flight details are known
            if prev == "STA":
                self.duties.append(Flight(self.lv["flight_number"],
                                          self.lv["dep"], self.lv["arr"],
                                          self.lv["STD"], self.lv["STA"],
                                          position=self.lv.get("position"),
                                          comeback=self.lv.get("comeback")))
                self.clean_up()

            # If not a flight but end/no time set, save as OtherDuty
            elif prev == "end_time" or self.lv.get("no_time"):
                self.duties.append(
                    OtherDuty(self.lv["other_duty"],
                              start_time=self.lv.get("start_time"),
                              end_time=self.lv.get("end_time"))
                )
                self.clean_up()

            # Off time set means end of of day so clean up
            if self.lv.get("off_time"):
                self.clean_up(end_of_duty=True)

    def full_period(self, month):
        """ Parse roster for every day in given period (month) """

        for day in month:
            self.day(day)

        # It might be that last duty was unfinished
        if len(self.duties) > 0:
            self.continued_duty = True  # TODO Finish up if last day of period
            self.clean_up(end_of_duty=True)


class ReadRoster:
    """ Parse html roster. """

    def __init__(self, source):
        self.source = source
        try:
            with open(self.source) as html:
                self.soup = BeautifulSoup(html.read(), "html.parser")
        except FileNotFoundError as file_error:
            print(file_error)
        else:
            self.run_file()

    def parse_html(self):
        """ Find every line in html roster with duty element.

        :return: Nested list with rows per column.
        """

        rows = []
        for row in self.soup.find_all("tr"):
            cells = [str(cell.string) for cell in row.find_all("td")]
            if len(cells) == 32:
                rows.append(cells)
        return [[row[column] for row in rows] for column in range(32)]

    def night_stops(self):
        """ Check box below roster days for any hotel information. """

        s = self.soup.find(string=re.compile(r"[A-Za-z]{6,12} HOTEL"))
        if s is not None:
            return re.findall(r"[A-Z][a-z]{2}[0-9]{2}", str(s.parent))

    def print_roster(self):
        """ Print roster for one file """

        total = num_flights = positioning = asby = 0
        ground_duties = domestic = days_flying = days_at_work = 0
        off_duty = {"LVE": 0, "SICK": 0, "ULV": 0}
        roster = ParseRoster()
        roster.full_period(self.parse_html())

        for i, duty_day in enumerate(roster.days, 1):
            on_asby = multi_pos = multi_gd = at_work = False

            # Skip empty days
            if duty_day is None:
                continue

            print(f"Day {i}")
            for duty in duty_day.duties:
                if isinstance(duty, Flight):
                    if not at_work:
                        days_at_work += 1
                        days_flying += 1
                        at_work = True
                    if duty.position:
                        if (not multi_pos
                                and ((duty.dep not in Flight.simulators
                                      and duty.arr not in Flight.simulators)
                                     or duty.distance > 15)):
                            # TODO Length not taken into account, only 1 leg per day
                            # TODO Ground pos to LGW and MXP not properly calculated
                            positioning += 1
                        multi_pos = True
                        print("    {} positioning duty from {} to {}"
                              .format(str(duty.position).capitalize(),
                                      duty.dep, duty.arr))
                    elif duty.comeback == "R":
                        print(f"    (This flight in {duty.dep} returned "
                              f"to stand while still on ground.)")
                    else:
                        total += duty.nominal
                        num_flights += 1
                        icao_d = duty.airports_list[duty.dep].icao
                        icao_a = duty.airports_list[duty.arr].icao
                        if icao_d.startswith("LF") and icao_a.startswith("LF"):
                            domestic += 1
                        print(f"    Flight from {duty.dep} to {duty.arr}, "
                              f"length {duty.length} nm ({duty.sector}).")
                        if on_asby:
                            asby -= 1
                            on_asby = False
                else:
                    roster_codes = get_rostercodes()
                    paid_codes = [code
                                  for code, values in roster_codes.items()
                                  if values[2] == "True"]
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
                        if (time_diff(duty.start_time, duty.end_time)
                                < timedelta(hours=4)):
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
            print(f"\nNightstopping {len(night_stops)} times: {nights}")

    def run_file(self):
        roster = ParseRoster()
        month = self.parse_html()
        master_count = {}

        # Convert raw roster into duties
        for day in month:
            roster.day(day)
        # Sum up duties of full period
        for day in roster.days:
            item_dict = day.count_items()
            for key, value in item_dict.items():
                try:
                    if key not in master_count:
                        master_count[key] = value
                    else:
                        master_count[key] = master_count[key] + value
                except TypeError:
                    # Key/value is bool
                    if key not in master_count:
                        master_count[key] = 1
                    else:
                        master_count[key] = master_count[key] + 1
        master_count["total"] = master_count["total"] / 10
        for key, value in master_count.items():
            print(f"Item {key} count {value}.")


if __name__ == '__main__':
    ReadRoster(rf"C:\Users\Rinze\Documents\Werk\rooster\2019\19-01.htm")

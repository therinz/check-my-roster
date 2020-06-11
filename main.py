import csv
import re
from datetime import timedelta

from bs4 import BeautifulSoup
from geopy.distance import great_circle


def main():
    while True:
        """ choice = str(input("\nChoose an action. Select 'a' to add an airport, "
                           "'r' to check a route, "
                           "'l' to list available airports or "
                           "'h' to read a html file or"
                           "'f' to add an airport from the big list, or"
                           "'q' to quit")).lower()"""
        choice = "h"
        if choice == "a":
            print(create_new_airport())
        elif choice == "r":
            check_flight_length()
        elif choice == "l":
            list_airports()
        elif choice == "h":
            y = validate_input("Specify year as yy", int, 10, 30)
            m = str(validate_input("Specify month in digits", int, 1, 12))
            if len(m) == 1:
                m = "0" + m
            rp = rf"C:\Users\Rinze\Documents\Werk\rooster\20{y}\{y}-{m}.htm"
            ReadRoster(rp)
        elif choice == "f":
            print(import_airport_data("PRG", 1))
        elif choice == "q":
            break
        else:
            print("{} is not a valid input.".format(choice))


def get_rostercodes():
    with open("other_duties.csv", "r", newline="") as f:
        contents = csv.reader(f, delimiter="|")
        return {row[0]: [row[1], row[2], row[3]] for row in contents}


def get_airports():
    with open("airports.csv", "r", newline="") as file:
        contents = csv.DictReader(file, delimiter="|")
        contents = sorted(contents, key=lambda row: row["Name"])
        return {row["IATA"]: Airport(row["IATA"], row["ICAO"],
                                     row["Name"], (row["LAT"], row["LONG"]))
                for row in contents}


class AirportNotKnown(Exception):
    def __init__(self, airport_list):
        self.airport_list = airport_list

    def __str__(self):
        return "Some airports are not defined: " + " ".join(self.airport_list)


class Airport:
    """ Create airport to call in various instances. """

    def __init__(self, iata, icao, name, coord):
        self.iata = iata
        self.icao = icao
        self.name = name
        self.coord = coord

    def __str__(self):
        return "{0} ({1}) is located at {2}.".format(self.name, self.iata,
                                                     (", ".join(map(str, self.coord))))


class DutyDay:
    """ Class containing several different duties on day, including start and end time if applicable. """

    def __init__(self, duties, report_time=None, off_duty=None):
        self.duties = duties
        self.start_time = report_time
        self.end_time = off_duty  # might be after midnight, thus < std
        # standby start will be before report time


class Flight:
    """ Flight used to distance between 2 places on duty day. """
    airports_list = get_airports()
    simulators = ["XBH", "XCS", "XDH", "XWT", "XSW", "XOL"]

    def __init__(self, flight_no, dep, arr, std, sta,
                 position=False, comeback=False):
        self.comeback = comeback
        self.flight_no = flight_no
        self.arr = arr
        self.dep = dep
        self.position = position
        self.sta = sta  # might be after midnight, thus < std
        self.sta = std
        for IATA in self.dep, self.arr:
            if not Flight.airports_list.get(IATA):
                Flight.airports_list[IATA] = import_airport_data(IATA)

    def distance(self):
        if self.comeback == "R":
            sector = "Ground return"
            length = 0
        else:
            length = int(great_circle(
                Flight.airports_list[self.dep].coord,
                Flight.airports_list[self.arr].coord).nautical)
            if length <= 400:
                sector = "s"
            elif length <= 1000:
                sector = "m"
            elif length <= 1500:
                sector = "l"
            else:
                sector = "xl"
        return length, sector


class OtherDuty:
    """ Create a class of any duty other than a flight. """
    rostercodes = get_rostercodes()

    def __init__(self, rostercode, start_time=None, end_time=None):
        self.rostercode = rostercode
        self.start_time = start_time
        self.end_time = end_time


def time_diff(a, b):
    # Does not take into account if same time different day
    def transpose(x): return int("".join([x[0:2], x[3:5]]))
    day = 0 if transpose(a) <= transpose(b) else 1
    a = a.split(":")
    b = b.split(":")
    return (timedelta(days=day, hours=int(b[0]), minutes=int(b[1]))
            - timedelta(days=0, hours=int(a[0]), minutes=int(a[1])))


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


def validate_input(prompt, type_=None, min_=None, max_=None):
    """ Request user input and clean it before return.

    :param prompt: Question to ask user.
    :param type_: Type of value asked. str, int, float.
    :param min_: Minimum length of str of lower value of int.
    :param max_: Maximum length of str of upper value of int.
    :return: str, int or float.
    """
    if min_ is not None and max_ is not None and max_ < min_:
        raise ValueError("min_ must be less than or equal to max_.")
    while True:
        ui = input(prompt)
        if type_ is not None:
            try:
                ui = type_(ui)
            except ValueError:
                print("Input type must be {}".format(type_.__name__))
                continue
        if isinstance(ui, str):
            ui_num = len(ui)
        else:
            ui_num = ui
        if max_ is not None and ui_num > max_:
            print("Input must be less than or equal to {}.".format(max_))
        elif min_ is not None and ui_num < min_:
            print("Input must be more than or equal to {}.".format(min_))
        else:
            return ui


def import_airport_data(iata, write=1):
    with open("all_airports.csv", "r", newline="", encoding='utf-8') as file:
        contents = csv.DictReader(file)
        for row in contents:
            if row["iata_code"] == iata.upper():
                apd = Airport(row["iata_code"], row["gps_code"], row["municipality"],
                              (row["latitude_deg"], row["longitude_deg"]))
                break
        try:
            if write == 1:
                with open("airports.csv", "a", newline="") as file2:
                    file_writer = csv.writer(file2, delimiter="|")
                    file_writer.writerow([apd.iata, apd.icao, apd.name, apd.coord[0], apd.coord[1]])
            return apd
        except NameError:
            print(f"Airport {iata} not found in big list")


def create_new_airport():
    """ Ask user for airport data and export it to airports.csv. """
    print("Create a new aiport with the next 5 questions")
    iata = validate_input("Type 3 letter IATA code", str.upper, 3, 3)
    airports_dict = get_airports()
    if airports_dict.get(iata):
        return f"Airport {iata} already in list"
    icao = validate_input("Type 4 letter ICAO code", str.upper, 4, 4)
    name = validate_input("Type name of airport", str.title, 2, 30)
    lat = validate_input("Type latitude as 1.234567", float)
    long = validate_input("Type longitude as 1.234567", float)
    with open("airports.csv", "a", newline="") as file:
        filewriter = csv.writer(file, delimiter="|")
        filewriter.writerow([iata, icao, name, lat, long])
    return Airport(iata, icao, name, (lat, long))


def check_flight_length():
    """ Ask user for 2 airports and print great circle distance. """
    apt_a = validate_input("Type first IATA", str.upper, 3, 3)
    apt_b = validate_input("Type second IATA code", str.upper, 3, 3)
    airports_dict = get_airports()
    distance = int(great_circle(airports_dict[apt_a].coord, airports_dict[apt_b].coord).nautical)
    print("The distance between {0} and {1} is {2} nautical miles.".format(airports_dict[apt_a].name,
                                                                           airports_dict[apt_b].name,
                                                                           distance))


def list_airports():
    airports_dict = get_airports()
    print("Available airports are:")
    for airport in airports_dict.values():
        print("{0} ({1})".format(airport.name, airport.iata))


if __name__ == '__main__':
    main()

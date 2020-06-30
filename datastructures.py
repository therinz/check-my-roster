import csv
from datetime import timedelta

from geopy.distance import great_circle


def get_rostercodes():
    """Load roster codes from small csv."""

    with open("other_duties.csv", "r", newline="") as f:
        contents = csv.reader(f, delimiter="|")
        return {row[0]: [row[1], row[2], row[3]]
                for row in contents}


def get_airports():
    """Load airports from frequent airports csv."""

    with open("airports.csv", "r", newline="") as file:
        contents = csv.DictReader(file, delimiter="|")
        contents = sorted(contents, key=lambda row: row["Name"])

        return {row["IATA"]: Airport(row["IATA"],
                                     row["ICAO"],
                                     row["Name"],
                                     (row["LAT"], row["LONG"]))
                for row in contents}


def time_diff(a, b):
    """Calculate time difference between two times.

    :returns: timedelta object time in hh:mm
    """

    def transpose(x): return int("".join([x[0:2], x[3:5]]))

    # If b is smaller it means a was previous day
    day = 0 if transpose(a) <= transpose(b) else 1
    a = a.split(":")
    b = b.split(":")

    return (timedelta(days=day, hours=int(b[0]), minutes=int(b[1]))
            - timedelta(days=0, hours=int(a[0]), minutes=int(a[1])))


def import_airport_data(iata, write=1):
    """Lookup airport data in big list and save in selected airport list."""

    with open("all_airports.csv", "r", newline="", encoding='utf-8') as file:
        contents = csv.DictReader(file)
        apd = None

        for row in contents:
            if row["iata_code"] == iata.upper():
                apd = Airport(row["iata_code"],
                              row["gps_code"],
                              row["municipality"],
                              (row["latitude_deg"], row["longitude_deg"]))
                break
        if not apd:
            raise AirportNotKnown([iata])

        if write == 1:
            with open("airports.csv", "a", newline="") as file2:
                file_writer = csv.writer(file2, delimiter="|")
                file_writer.writerow([apd.iata,
                                      apd.icao,
                                      ascii(apd.name).replace("'", ""),
                                      apd.coord[0], apd.coord[1]])
        return apd


class Airport:
    """Class to store data relating to an airport."""

    def __init__(self, iata, icao, name, coord):
        self.iata = iata
        self.icao = icao
        self.name = name
        self.coord = coord

    def __str__(self):
        return (f"{self.name} ({self.iata}) is located at "
                f"{', '.join(map(str, self.coord))}.")


class DutyDay:
    """
    Class containing several different duties on day,
    including start and end time if applicable.
    """

    def __init__(self, duties, report_time=None, off_duty=None):
        self.duties = duties
        self.start_time = report_time
        self.end_time = off_duty  # might be after midnight, thus < std
        # TODO standby start will be before report time
        self.count = self.count_items()

    def count_items(self):
        """Count the different items of the duties on 1 day."""

        on_asby = multi_ground = False
        lv = dict.fromkeys(["num_sectors", "num_flights", "domestic", "asby"],
                           0)

        for duty in self.duties:
            if isinstance(duty, Flight):
                lv["day_at_work"] = lv["flying"] = True

                # First check if positioning
                if duty.position and "positioning" not in lv:
                    if ((duty.dep not in Flight.simulators
                         and duty.arr not in Flight.simulators)
                            or duty.length > 15):
                        # Length of sector not taken into account,
                        # only 1 leg per day. Not to sim if less than 15nm.
                        # TODO Ground pos to LGW and MXP not properly calculated
                        lv["positioning"] = True

                # Normal flight
                else:
                    lv["num_sectors"] += duty.nominal
                    lv["num_flights"] += 1
                    lv["domestic"] += 1 if duty.domestic else 0

                    # Call out from asby
                    if on_asby:
                        lv["asby"] -= 1
                        on_asby = False
            else:
                # First check if day at home
                if duty.duty_code in OtherDuty.off_codes:
                    lv[duty.duty_code] = 1

                # Only 1 ground duty per day paid
                if duty.paid and not multi_ground:
                    lv["ground_duties"] = 1
                    lv["day_at_work"] = True
                    multi_ground = True
                if duty.duty_code in ["ASBY", "ADTY"]:
                    lv["day_at_work"] = on_asby = True
                    lv["asby"] += duty.paid
        return lv

    def __str__(self):
        return f"Duty day consisting of {len(self.duties)} duties."


class Flight:
    """Contains information about flight between 2 airports."""

    # Populate list with frequent EZY airports
    airports_list = get_airports()
    simulators = ["XBH", "XCS", "XDH", "XWT", "XSW", "XOL"]
    # Factored length of duty, multiplied by 10
    conversion = {"s": 8, "m": 12, "l": 15, "xl": 25}

    def __init__(self, flight_no, dep, arr, std, sta,
                 position=False, comeback=False):

        # First check if airport in small list, else import from big list
        for iata in dep, arr:
            if iata not in Flight.airports_list:
                Flight.airports_list[iata] = import_airport_data(iata)

        self.comeback = comeback
        self.flight_no = flight_no
        self.dep = Flight.airports_list[dep]
        self.arr = Flight.airports_list[arr]
        self.position = position
        self.sta = sta  # might be after midnight, thus < std
        self.sta = std
        self.domestic = (self.dep.icao[:2] == self.arr.icao[:2])
        self.length, self.sector, self.nominal = self.distance()

    def distance(self):
        """
        Calculate distance between 2 airports and return this value as
        length, sector length category and nominal length.
        """

        # Skip the calculation if no take off
        if self.comeback == "R":
            sector = "Ground return"
            length = nominal = 0
        else:
            length = int(great_circle(self.dep.coord, self.arr.coord).nautical)
            if length <= 400:
                sector = "s"
            elif length <= 1000:
                sector = "m"
            elif length <= 1500:
                sector = "l"
            else:
                sector = "xl"
            nominal = self.conversion[sector]
        return length, sector, nominal

    def __str__(self):
        if self.position:
            return (f"{str(self.position).capitalize()} positioning "
                    f"duty from {self.dep.iata} to {self.arr.iata}.")
        elif self.comeback == "R":
            return (f"(A flight in {self.dep.iata} returned to stand "
                    f"while still on ground.)")
        elif self.comeback == "A":
            return (f"Flight from {self.dep.iata} to {self.arr.iata} which "
                    f"returned or diverted. Length of {self.length}nm "
                    f"({self.sector}).")
        else:
            return (f"Flight from {self.dep.iata} to {self.arr.iata}, length "
                    f"of {self.length}nm ({self.sector}).")


class OtherDuty:
    """Class of any duty other than a flight."""

    rostercodes = get_rostercodes()
    paid_codes = [code for code, values in rostercodes.items()
                  if values[2] == "True"]
    off_codes = [code for code, values in rostercodes.items()
                 if values[1] == "off"]
    gnd_training = [code for code, values in rostercodes.items()
                    if (values[1] in ["training", "recurrent"]
                        and values[2] == "True")]

    def __init__(self, duty_code, start_time=None, end_time=None):
        self.duty_code = duty_code
        self.start_time = start_time
        self.end_time = end_time
        self.paid = (duty_code in OtherDuty.paid_codes)
        self.off = (duty_code in OtherDuty.off_codes)

        # Check how much sectors paid out
        if self.paid:
            if self.duty_code in ["ADTY", "ASBY", "OFC4", "OFC8"]:
                short = (time_diff(self.start_time, self.end_time)
                         < timedelta(hours=4))
                self.paid = 1 if short else 2
            elif self.duty_code in OtherDuty.gnd_training:
                self.paid = 1

    def __str__(self):
        if not self.paid:
            return f"No paid duty: {self.duty_code}."
        else:
            return (f"Ground duty with code {self.duty_code} "
                    f"({self.paid} sector(s) paid).")


class AirportNotKnown(Exception):
    """Custom message if number of airports not known."""

    def __init__(self, airport_list):
        self.airport_list = airport_list

    def __str__(self):
        return "Some airports are not defined: " + " ".join(self.airport_list)


# FUNCTIONS BELOW NOT USED

def create_new_airport():
    """Ask user for airport data and export it to airports.csv."""

    print("Create a new airport with the next 5 questions")
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
    distance = int(great_circle(airports_dict[apt_a].coord,
                                airports_dict[apt_b].coord)
                   .nautical)
    print("The distance between {0} and {1} is {2} nautical miles."
          .format(airports_dict[apt_a].name,
                  airports_dict[apt_b].name,
                  distance))


def list_airports():
    airports_dict = get_airports()
    print("Available airports are:")
    for airport in airports_dict.values():
        print(f"{airport.name} ({airport.iata})")


def validate_input(prompt, type_=None, min_=None, max_=None):
    """ Request user input and clean it before return.

    :param prompt: Question to ask user.
    :param type_: Type of value asked. str, int, float.
    :param min_: Minimum length of str of lower value of int.
    :param max_: Maximum length of str of upper value of int.
    :return: str, int or float.
    """
    if (min_ is not None
            and max_ is not None
            and max_ < min_):
        raise ValueError("min_ must be less than or equal to max_.")
    while True:
        ui = input(prompt)
        if type_ is not None:
            try:
                ui = type_(ui)
            except ValueError:
                print(f"Input type must be {type_.__name__}")
                continue
        if isinstance(ui, str):
            ui_num = len(ui)
        else:
            ui_num = ui
        if max_ is not None and ui_num > max_:
            print(f"Input must be less than or equal to {max_}.")
        elif min_ is not None and ui_num < min_:
            print(f"Input must be more than or equal to {min_}.")
        else:
            return ui

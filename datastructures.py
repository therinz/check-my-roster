import csv
from datetime import timedelta

from geopy.distance import great_circle


def get_rostercodes():
    """ Load roster codes from csv. """

    with open("other_duties.csv", "r", newline="") as f:
        contents = csv.reader(f, delimiter="|")
        return {row[0]: [row[1], row[2], row[3]]
                for row in contents}


def get_airports():
    """ Load airports from frequent airports csv. """

    with open("airports.csv", "r", newline="") as file:
        contents = csv.DictReader(file, delimiter="|")
        contents = sorted(contents, key=lambda row: row["Name"])

        return {row["IATA"]: Airport(row["IATA"],
                                     row["ICAO"],
                                     row["Name"],
                                     (row["LAT"], row["LONG"]))
                for row in contents}


def time_diff(a, b):
    # TODO Does not take into account if same time different day
    def transpose(x): return int("".join([x[0:2], x[3:5]]))
    day = 0 if transpose(a) <= transpose(b) else 1
    a = a.split(":")
    b = b.split(":")
    return (timedelta(days=day, hours=int(b[0]), minutes=int(b[1]))
            - timedelta(days=0, hours=int(a[0]), minutes=int(a[1])))


def import_airport_data(IATA, write=1):
    """ Lookup airport data in big list and save in selected airport list. """

    with open("all_airports.csv", "r", newline="", encoding='utf-8') as file:
        contents = csv.DictReader(file)

        for row in contents:
            if row["iata_code"] == IATA.upper():
                apd = Airport(row["iata_code"],
                              row["gps_code"],
                              row["municipality"],
                              (row["latitude_deg"], row["longitude_deg"]))
                break
            else:
                raise AirportNotKnown([IATA])

        if write == 1:
            with open("airports.csv", "a", newline="") as file2:
                file_writer = csv.writer(file2, delimiter="|")
                file_writer.writerow([apd.iata,
                                      apd.icao,
                                      apd.name,
                                      apd.coord[0], apd.coord[1]])

        return apd


class Airport:
    """ Class to store data relating to an airport. """

    def __init__(self, iata, icao, name, coord):
        self.iata = iata
        self.icao = icao
        self.name = name
        self.coord = coord

    def __str__(self):
        return ("{} ({}) is located at {}."
                .format(self.name, self.iata,
                        (", ".join(map(str, self.coord)))
                        )
                )


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


class Flight:
    """ Flight used to distance between 2 airports. """

    # Populate list with frequent EZY airports
    airports_list = get_airports()
    simulators = ["XBH", "XCS", "XDH", "XWT", "XSW", "XOL"]
    # Factored length of duty, multiplied by 10
    nominal = {"s": 8, "m": 12, "l": 15, "xl": 25}

    def __init__(self, flight_no, dep, arr, std, sta,
                 position=False, comeback=False):
        self.comeback = comeback
        self.flight_no = flight_no
        self.arr = arr
        self.dep = dep
        self.position = position
        self.sta = sta  # might be after midnight, thus < std
        self.sta = std

        # If airport data not known, import from big list
        for IATA in self.dep, self.arr:
            if not Flight.airports_list.get(IATA):
                Flight.airports_list[IATA] = import_airport_data(IATA)

    def distance(self):
        # Skip the calculation if no take off
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


class AirportNotKnown(Exception):
    """ Custom message if number of airports not known. """

    def __init__(self, airport_list):
        self.airport_list = airport_list

    def __str__(self):
        return "Some airports are not defined: " + " ".join(self.airport_list)


# FUNCTIONS BELOW NOT USED

def create_new_airport():
    """ Ask user for airport data and export it to airports.csv. """

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

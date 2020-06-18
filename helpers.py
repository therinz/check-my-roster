import csv

from geopy.distance import great_circle
from datastructures import Airport
from datetime import timedelta


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


def time_diff(a, b):
    # Does not take into account if same time different day
    def transpose(x): return int("".join([x[0:2], x[3:5]]))
    day = 0 if transpose(a) <= transpose(b) else 1
    a = a.split(":")
    b = b.split(":")
    return (timedelta(days=day, hours=int(b[0]), minutes=int(b[1]))
            - timedelta(days=0, hours=int(a[0]), minutes=int(a[1])))


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
        print("{0} ({1})".format(airport.name, airport.iata))

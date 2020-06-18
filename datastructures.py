from helpers import get_rostercodes, get_airports, import_airport_data
from geopy.distance import great_circle


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
        return "{} ({}) is located at {}.".format(self.name,
                                                  self.iata,
                                                  (", ".join(map(str,
                                                                 self.coord))))


class DutyDay:
    """
    Class containing several different duties on day,
    including start and end time if applicable.
    """

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



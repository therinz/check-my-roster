
#  Copyright (c) 2020. Rinze Douma

import re
from collections import defaultdict

from datetime import timedelta
from bs4 import BeautifulSoup

from datastructures import DutyDay, Flight, OtherDuty, get_rostercodes
from datastructures import time_diff, summary_description

GND_POS = ["OWN", "TAXI", "TRN", "NSO"]


class ParseRoster:
    """Class to convert items on roster to countable values."""

    roster_codes = get_rostercodes()
    timed_roster_codes = [code
                          for code, values in roster_codes.items()
                          if values[0] == "True"]
    skip_vals = ["None", " EJU", " ", "Block", "Duty", " OWNA",
                 "(320)", "(321)", "EZS", " EZS", "SNCR"]
    cont_times = ["report_time", "start_time", "STD", "STA"]

    def __init__(self):
        """
        :param self.lv: Store local values for working on roster decryption.
        :param self.duties: Store each duty as a Flight or OtherDuty class."""
        self.continued_duty = False
        self.lv = {}
        self.duties = []
        self.days = []

    def results(self, period):
        """Take list of roster days and return list of DutyDay objects.

        :param period: List of list containing rows with duty elements.
        :return: List of DutyDay objects."""

        # Convert raw roster into days-list
        for d in period:
            self.parse_day(d)
        # It might be that last duty was unfinished
        if self.lv.get("previous_item") in ParseRoster.cont_times:
            self.continued_duty = True
        # No activity in progress, but still duties in cache
        elif len(self.duties) > 0:
            self.clean_up(end_of_duty=True)

        return self.days

    def search_duty_type(self, row):
        """Interpret what item in current row is."""

        search_flight_number = re.search(r"[0-9]{3,4}", row)
        search_non_flight = re.search(r"[A-Z/]{3,4}", row)

        # Ground positioning
        if row in GND_POS:
            # Takes into account taxi between bases. Flt no used for switching
            self.lv["position"] = "ground"
            self.lv["flight_number"] = row

        # Flight
        elif search_flight_number:
            self.lv["flight_number"] = search_flight_number.group()

            # Either ground or air return, instead of scheduled route
            if row[-1] == "R" or row[-1] == "A":
                self.lv["comeback"] = row[-1]

            # If end_time set, it means a duty from previous day is not saved.
            if self.lv.get("end_time"):
                self.clean_up()

        # Other duty type
        elif search_non_flight and "flight_number" not in self.lv:
            self.lv["other_duty"] = search_non_flight.group()

            # Many other duties do not have times associated.
            if self.lv["other_duty"] not in ParseRoster.timed_roster_codes:
                self.lv["no_time"] = True

    def time_details(self, search_time, prev):
        """Interpret current time type by switching based on previous."""

        switch = {"report_time": "STD",
                  "STD": "STA",
                  "start_time": "end_time"}

        # Flight in progress
        if "flight_number" in self.lv:
            time_type = switch.get(prev, "report_time")

        # Timed duty other than a flight
        elif "other_duty" in self.lv:
            # Some duties like ADTY with call out have 2 start times
            if self.lv.get("start_time") == search_time:
                time_type = "report_time"
            elif "start_time" in self.lv:
                time_type = "end_time"
            else:
                time_type = "start_time"

        # After flight or flight-stby
        else:
            time_type = "off_time"

        self.lv[time_type] = search_time
        self.lv["previous_item"] = time_type

    def flight_details(self, row, search_iata):
        """Determine whether flight is a positioning duty and set dep/arr."""

        if self.lv.get("position") != "ground" and re.search(r"\*", row):
            self.lv["position"] = "air"

        # Set departure and arrival airfields
        if "dep" not in self.lv:
            self.lv["dep"] = search_iata.group()
        else:
            self.lv["arr"] = search_iata.group()

    def clean_up(self, end_of_duty=False, keep_duty_type=False):
        """
        Delete values in lv cache. Method may be called on start of new
        day because previous day was unfinished, as set by keep_duty_type.
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
                if "other_duty" in self.lv:
                    save_vals["other_duty"] = self.lv["other_duty"]
                elif "flight_number" in self.lv:
                    save_vals["flight_number"] = self.lv["flight_number"]

        # One duty has finished, not the day completely
        else:
            report = self.lv.get("report_time")
            if report:
                save_vals.update({"report_time": report,
                                  "previous_item": "report_time"})

            # If last time > 9h end previous duty day
            previous = self.lv.get("previous_item")
            if previous:
                save_vals.update({"last_time": self.lv[previous],
                                  "last_type": previous})
            elif "no_time" in self.lv:
                save_vals.update({"last_type": "no_time"})

        # Clear local values and save new data
        self.lv.clear()
        self.lv.update(save_vals)

    def parse_day(self, day): # NOQA
        """For one day, loop through all rows and extract duties and times."""

        skip_row = end_of_duty = 0
        for row_num, row in enumerate(day):
            previous_item = self.lv.get("previous_item")

            # Skip block & duty times at end of day
            if (row_num > (len(day) - 4)
                    or (end_of_duty and row_num > end_of_duty + 2)):
                break
            # Skip empty and non-relevant rows
            elif row in ParseRoster.skip_vals or len(row) < 3:
                skip_row += 1
                # More than 3 empty rows means no more items that day
                if skip_row > 3:
                    # There may still be an unfinished duty in cache
                    if (len(self.duties) > 0
                            and previous_item not in ParseRoster.cont_times):
                        self.clean_up(end_of_duty=True)
                    break
                continue
            skip_row = end_of_duty = 0

            # Check what's happening on row
            self.search_duty_type(row)
            search_time = re.search(r"[0-9]{2}:[0-9]{2}", row)

            # If current row is a time, check what type of activity
            if search_time:
                time = search_time.group()

                # If new day but still values in cache, save those first.
                ongoing = (self.lv.get("last_type") == "off_time"
                           or self.lv.get("last_type") == "end_time")
                if (ongoing and (time_diff(self.lv["last_time"], time)
                                 > timedelta(hours=9))):
                    self.clean_up(end_of_duty=True, keep_duty_type=True)

                # Determine what type of time we're dealing with
                self.time_details(time, previous_item)
                previous_item = self.lv.get("previous_item")

            # Fetch details about flight
            elif "flight_number" in self.lv and row not in GND_POS:
                search_iata = re.search(r"[A-Z]{3}\Z", row)
                if search_iata:
                    self.flight_details(row, search_iata)
                    continue

            # When STA is set, all flight details are known so save duty
            if previous_item == "STA":
                self.duties.append(Flight(self.lv["flight_number"],
                                          self.lv["dep"], self.lv["arr"],
                                          self.lv["STD"], self.lv["STA"],
                                          position=self.lv.get("position"),
                                          comeback=self.lv.get("comeback")))
                self.clean_up()

            # If not a flight but end/no time set, save as OtherDuty
            elif previous_item == "end_time" or "no_time" in self.lv:
                self.duties.append(
                    OtherDuty(self.lv["other_duty"],
                              start_time=self.lv.get("start_time"),
                              end_time=self.lv.get("end_time"))
                )
                self.clean_up()

            # Off time set means end of of day so clean up
            if "off_time" in self.lv:
                self.clean_up(end_of_duty=True)
                end_of_duty = row_num


def read_html(source):
    """Read html file and return nested list with rows per column."""

    # First try to open html file.
    try:
        with open(source) as html:
            soup = BeautifulSoup(html.read(), "html.parser")
    except FileNotFoundError:
        exit("File not found!")

    # Find the relevant cells and convert to strings
    rows = []
    for row in soup.find_all("tr"):
        cells = [str(cell.string) for cell in row.find_all("td")]

        # Turns out each row of the actual roster is 32 cells wide
        if len(cells) == 32:
            rows.append(cells)

    # Transpose rows to columns
    return [[row[column] for row in rows] for column in range(32)]


def night_stops(soup):
    """Check box below roster table for any hotel information."""

    s = soup.find(string=re.compile(r"[A-Za-z]{6,12} HOTEL"))
    if s is not None:
        return re.findall(r"[A-Z][a-z]{2}[0-9]{2}", str(s.parent))


def only_count(days): # NOQA
    """Take list of days and return count of roster items.

    :param days: List of DutyDay objects.
    :return: Dictionary of roster items with their count."""

    master_count = defaultdict(int)

    # Sum up duties of full period
    for d in days:
        activities = d.count_items()
        for key, value in activities.items():
            try:
                master_count[key] += value
            except TypeError:
                # Key/value is bool
                master_count[key] += 1
    master_count["num_sectors"] = master_count["num_sectors"] / 10 # NOQA

    return summary_description(master_count)


if __name__ == '__main__':
    months = []
    year = 17
    month_start = 8
    num_months = 1
    path = r"C:\Users\Rinze\Documents\Werk\rooster"
    for i in range(month_start, month_start + num_months):
        print(f"month {i}")
        file = rf"20{year}\{year}-{i:02d}.htm"
        months.extend(read_html(r"\\".join([path, file])))

    pr = ParseRoster()
    days = pr.results(months)
    for i, day in enumerate(days):
        print(f"Day {i+1}")
        for duty in day.duties:
            print(duty)

    print("")

    count = only_count(days)
    for k, v in count.items():
        print(f"{k}: {v}.")

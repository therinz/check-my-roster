
#  Copyright (c) 2020. Rinze Douma

import re

from datetime import timedelta
from bs4 import BeautifulSoup

from datastructures import DutyDay, Flight, OtherDuty, get_rostercodes
from datastructures import time_diff

GND_POS = ["OWN", "TAXI", "TRN", "NSO"]


class ParseRoster:
    """Read list of items on day of roster and return DutyDay with each Duty item.

    :param self.lv: Store local values for working on roster decryption
    :type self.lv: dict
    :param self.duties: Store each duty as a Flight or OtherDuty class
    :type self.duties: list
    :param self.duties: Store each day as a DutyDay class contain duties of
    Flight or Otherduty class
    :type self.duties: list
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
        """Interpret what item in row is."""

        search_flight_number = re.search(r"[0-9]{3,4}", row)
        search_non_flight = re.search(r"[A-Z/]{3,4}", row)

        # Ground positioning
        if row in GND_POS:
            # Takes into account taxi between bases.
            self.lv["position"] = "ground"
            self.lv["flight_number"] = True

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

        # Flight after stby
        elif self.lv.get("last_time_type") == "end_time":
            time_type = "report_time"

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

    def day(self, day):
        """For one day, loop through all rows and extract duties and times."""

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
                # More than 3 empty rows means no more items that day
                if i > 3:
                    # There may still be an unfinished duty in cache
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

                # If new day but still values in cache, save those first.
                unfinished = (self.lv.get("last_type") == "off_time"
                              or self.lv.get("last_type") == "end_time")
                if (unfinished and (time_diff(self.lv["last_time"], time)
                                    > timedelta(hours=9))):
                    self.clean_up(end_of_duty=True, keep_duty_type=True)

                # Determine what type of time we're dealing with
                self.time_details(time, previous)

            # Fetch details about flight
            elif "flight_number" in self.lv and row not in GND_POS:
                search_iata = re.search(r"[A-Z]{3}\Z", row)
                if search_iata:
                    self.flight_details(row, search_iata)
                    continue

            # When STA is set, all flight details are known
            prev = self.lv.get("previous_item")
            if prev == "STA":
                self.duties.append(Flight(self.lv["flight_number"],
                                          self.lv["dep"], self.lv["arr"],
                                          self.lv["STD"], self.lv["STA"],
                                          position=self.lv.get("position"),
                                          comeback=self.lv.get("comeback")))
                self.clean_up()

            # If not a flight but end/no time set, save as OtherDuty
            elif prev == "end_time" or "no_time" in self.lv:
                self.duties.append(
                    OtherDuty(self.lv["other_duty"],
                              start_time=self.lv.get("start_time"),
                              end_time=self.lv.get("end_time"))
                )
                self.clean_up()

            # Off time set means end of of day so clean up
            if "off_time" in self.lv:
                self.clean_up(end_of_duty=True)

    def full_period(self, month):
        """Parse roster for every day in given period (month)."""

        for day in month:
            self.day(day)

        # It might be that last duty was unfinished
        if len(self.duties) > 0:
            self.continued_duty = True  # TODO Finish up if last day of period
            self.clean_up(end_of_duty=True)


class ReadRoster:
    """Parse html roster."""

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
        """Find every line in html roster with duty element.

        :return: Nested list with rows per column.
        """

        rows = []
        for row in self.soup.find_all("tr"):
            cells = [str(cell.string) for cell in row.find_all("td")]
            if len(cells) == 32:
                rows.append(cells)
        return [[row[column] for row in rows] for column in range(32)]

    def night_stops(self):
        """Check box below roster days for any hotel information."""

        s = self.soup.find(string=re.compile(r"[A-Za-z]{6,12} HOTEL"))
        if s is not None:
            return re.findall(r"[A-Z][a-z]{2}[0-9]{2}", str(s.parent))

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
        master_count["num_sectors"] = master_count["num_sectors"] / 10
        for key, value in master_count.items():
            print(f"Item {key} count {value}.")


if __name__ == '__main__':
    for i in range(10,13):
        print(f"month {i}")
        ReadRoster(rf"C:\Users\Rinze\Documents\Werk\rooster\2016\16-{i:02d}.htm")
    #ReadRoster(rf"C:\Users\Rinze\Documents\Werk\rooster\2017\17-02.htm")

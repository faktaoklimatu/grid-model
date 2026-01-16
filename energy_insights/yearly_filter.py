"""
Provides filtering functionality for plotting yearly graphs (based on params dictionary).
"""

from typing import Optional, Union
from datetime import date

from .region import Region


def _parse_isoformat(days: list[Union[date, str]]) -> list[date]:
    """
    Returns the list of dates based on the provided list of isoformat strings.

    Arguments:
        days: list of string representation of days, in format YYYY-MM-DD.

    Returns:
        List of parsed dates.
    """
    return [
        day if isinstance(day, date) else date.fromisoformat(day)
        for day in days
    ]


def _get_weeks_from_days(days: list[date]) -> list[int]:
    """
    Returns the list of weeks based on the provided list of dates.

    Arguments:
        days: list of dates.

    Returns:
        List of ISO Week Numbers such that a week is in the output iff there is a day in this week
        in the input.
    """
    weeks: set[int] = set()
    for day in days:
        weeks.add(day.isocalendar().week)
    output = list(weeks)
    output.sort()
    return output


def _get_days_of_year(days: list[date]) -> list[int]:
    """
    Returns the list of days of year based on the provided list of dates.

    Arguments:
        days: list of dates.

    Returns:
        List of ordinal days of year (starting with 1) corresponding to input list of dates.
    """
    days_of_year: list[int] = []
    for day in days:
        delta = day - date(day.year, 1, 1)
        # First day of the year should be 1.
        days_of_year.append(delta.days + 1)
    return days_of_year


class YearlyFilter:
    """ Base interface for filtering weeks and regions for yearly plots.

    For simplicity, this interface does not take into account what year it is. All implementations
    must work correctly for ISO years with 52 and 53 weeks.
    """

    def __init__(self, regions: Optional[set[Region]]):
        self.regions = regions

    def get_weeks(self) -> list[int]:
        """
        Returns the desired weeks for this filter.

        Returns:
          List of int ISO Week Numbers
        """
        raise NotImplementedError()

    def get_days_of_year(self) -> Optional[list[int]]:
        """
        Returns the desired days for this filter. Those days must lie within the weeks returned by
        `get_weeks()`.

        Returns:
          List of ordinal days of year (starting with 1). None denotes all days within the returned
          weeks (no additional filter applied).
        """
        return None

    def filter_regions(self, regions: set[Region]) -> set[Region]:
        """
        Returns the desired regions out of all provided `regions`.

        Returns:
            Set of regions that are part of this filter.
        """
        if self.regions is None:
            return regions
        return self.regions & regions

    @staticmethod
    def build(params):
        """ Static constructor based on a params dictionary. """
        countries = None
        if "countries" in params:
            countries = set(params["countries"])

        if "week_sampling" in params:
            return PeriodicYearlyFilter(countries, params["week_sampling"])
        if "weeks" in params:
            return StaticYearlyFilter(countries, params["weeks"])
        if "days" in params:
            dates = _parse_isoformat(params["days"])
            return StaticYearlyFilter(countries,
                                      weeks=_get_weeks_from_days(dates),
                                      days_of_year=_get_days_of_year(dates))
        raise ValueError("Invalid params provided to YearlyFilter.")


class StaticYearlyFilter(YearlyFilter):
    """ Returns a given list of ISO Week numbers. """

    def __init__(self,
                 regions: Optional[set[Region]],
                 weeks: list[int],
                 days_of_year: Optional[list[int]] = None):
        super().__init__(regions)
        self.weeks = weeks
        self.days_of_year = days_of_year

    def get_weeks(self) -> list[int]:
        return self.weeks

    def get_days_of_year(self) -> Optional[list[int]]:
        return self.days_of_year


class PeriodicYearlyFilter(YearlyFilter):
    """ Returns every n-th week, based on a given parameter ``n``.

    Ignores the first and the last week to make sure all weeks are complete.
    """
    min_week = 2
    max_week = 51

    def __init__(self, regions: Optional[set[Region]], week_sampling: int):
        super().__init__(regions)
        self.week_sampling = week_sampling

    def get_weeks(self) -> list[int]:
        weeks = []
        for week in range(PeriodicYearlyFilter.min_week, PeriodicYearlyFilter.max_week + 1):
            if week % self.week_sampling == 0:
                weeks.append(week)
        return weeks

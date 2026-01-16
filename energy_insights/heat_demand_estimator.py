"""
Provides interpolated hourly heat demand values based on provided temperature and demand profiles.
"""

from pathlib import Path
from typing import Union

import pandas as pd
import numpy as np
from scipy import stats

from .region import Zone


class HeatDemandEstimator:
    """
    Helper class that loads monthly heat demand profiles and estimates hourly heat demand (in MW)
    based on provided hourly temperatures data set.
    """

    def __init__(
        self,
        data_path: Union[str, Path],
    ) -> None:
        self.data_path = Path(data_path)

    def _get_path(self, country: Zone) -> Path:
        return self.data_path / "heat_demand" / f"{country}-monthly.csv"

    def _load_monthly_heat_demand(self, country: Zone, year: int) -> pd.DataFrame:
        """
        Loads and returns monthly heat demand.

        Arguments:
            country: Zone to load heat demand for.
            year: Relevant year that specifies slice of the heat demand that is returned.

        Returns: The data frame for monthly heat demand for specified country and year.
        """
        df = pd.read_csv(self._get_path(country), index_col='month')
        return df[df["year"] == year]

    def _compute_daily_heating_season(self, hourly_temperatures: pd.DataFrame) -> pd.DataFrame:
        """
        For provided dataframe with hourly temperatures, return a data frame encoding which days
        fall into the heating season.

        By Czech law, heating season is started when the average daily temperatures for two
        consecutive days are below 13 degree Celsius and the forecast for the next day suggests the
        average daily temperature will again be below 13 degrees. We approximate it by making
        the look-ahead based on the real average temperature for the next day.

        Similarly, heating season is interrupted / stopped, when the average daily temperatures for
        two consecutive days are above 13 degree Celsius and the forecast for the next day suggests
        the average daily temperature will again be above 13 degrees.

        Arguments:
            hourly_temperatures: Temperatures for each hour of a year (in "temperatures" column).

        Returns:
            New data frame (indexed by integer day of year) with a single boolean column "season",
            informing for each day of the year whether it falls in the heating season.
        """
        daily = (
            hourly_temperatures.groupby("day")["temperature"]
            .mean().rename("mean_temperature").to_frame()
        )

        # Add helper values to properly compute the heating season.
        daily["last_mean_temperature"] = daily['mean_temperature'].shift(1)
        daily["next_mean_temperature"] = daily['mean_temperature'].shift(-1)
        # Compute signals to turn heating season on/off.
        daily["season_turn_on"] = (daily["mean_temperature"] < 13) & (
            daily["last_mean_temperature"] < 13) & (daily["next_mean_temperature"] < 13)
        daily["season_turn_off"] = (daily["mean_temperature"] > 13) & (
            daily["last_mean_temperature"] > 13) & (daily["next_mean_temperature"] > 13)

        # Based on the signals, compute the heating season.
        def compute_season(state):
            def inner(x):
                season = state["season"]
                if not season and x["season_turn_on"]:
                    season = True
                elif season and x["season_turn_off"]:
                    season = False
                return season
            # Capture state dictionary to be reused across multiple calls to inner.
            return inner

        # Assuming Jan 01 is within the heating season.
        state = {"season": True}
        return daily.apply(compute_season(state), axis=1).rename("season").to_frame()

    def _compute_degree_hours(self, hourly_temperatures: pd.DataFrame) -> pd.DataFrame:
        """
        Compute and return degree hours for each hour in the provided temperatures data frame.

        Degree hours for each hour in a heating season are defined as the difference of the
        outside temperature to a given nominal temperature (we use standard 18 °C as used
        across Europe) and is defined as 0 for each hour outside of the heating season.

        Arguments:
            hourly_temperatures: Temperatures for each hour of a year (in "temperatures" column).

        Returns:
            A copy of the provided data frame, adding 3 columns:
            - "day": (1-365 or 366) - day of year,
            - "month": (1-12),
            - "season": bool - whether given hour falls within heating season,
            - "degree_hours": float - number of degree hours in the given hour.
        """
        temperatures = pd.DataFrame(hourly_temperatures)
        temperatures["day"] = temperatures.index.day_of_year
        temperatures["month"] = temperatures.index.month

        temperatures = temperatures.join(self._compute_daily_heating_season(temperatures), on="day")
        temperatures["degree_hours"] = (
            np.where(temperatures["season"], 18 - temperatures["temperature"], 0)
        )
        temperatures["degree_hours"] = temperatures["degree_hours"].clip(lower=0)

        return temperatures

    def get_heat_demand_MW(self,
                           historic_hourly_temperatures: pd.DataFrame,
                           current_hourly_temperatures: pd.DataFrame,
                           country: Zone,
                           year: int) -> pd.Series:
        """
        Estimate and return hourly heat demand for a given country and year.

        The heat demand is estimated from aggregate monthly heat demands, based on the provided data
        set of hourly temperatures. It uses a proxy metric of degree days (in our case degree hours)
        that is commonly used to estimate heat demand. We use linear regression on the monthly heat
        demand and monthly degree-hours to estimate the additional heat demand for each additional
        degree hour.

        This then allows computing base heat demand for each month and finally the heat demand of
        each hour in the year.

        Arguments:
            historic_hourly_temperatures: Temperatures for each hour of
                the year (in "temperatures" column) of the historic
                weather year from which parameters are estimated.
            current_hourly_temperature: Temperatures for each hour of
                the year for which heat demand is to be estimated.
            country: Zone to estimate heat demand for.
            year: Year to estimate heat demand for.

        Returns:
            a series with estimated heat demand for each hour (that exists in the index of
            `hourly_temperatures` and falls within specified `year`).
        """
        historic_temperatures = self._compute_degree_hours(historic_hourly_temperatures)
        current_temperatures = self._compute_degree_hours(current_hourly_temperatures)

        # Construct a data frame with monthly degree hours and monthly demand and compute slope of
        # a linear regression (how much TJ of heat demand adds every degree hour).
        monthly = (
            historic_temperatures.groupby("month")["degree_hours"]
            .sum().rename("monthly_degree_hours").to_frame()
        )

        monthly_heat_demand = self._load_monthly_heat_demand(country, year)
        if monthly_heat_demand.empty:
            raise ValueError(f"Could not load monthly heat demand for {country} in {year}")

        monthly = monthly.join(monthly_heat_demand, on="month")
        slope_TJ_per_degree_hour, _, _, _, _ = stats.linregress(
            monthly["monthly_degree_hours"], monthly["monthly_demand_TJ"])

        # Compute base heat demand for each month.
        def compute_monthly_heat_baseload(month):
            monthly_variable_TJ = slope_TJ_per_degree_hour * month["monthly_degree_hours"]
            return month["monthly_demand_TJ"] - monthly_variable_TJ
        monthly_baseloads = monthly.apply(compute_monthly_heat_baseload, axis=1).to_dict()

        # To properly spread the base heat demand to every hour of a month, we need the number of
        # hours per month.
        hours_per_month = current_temperatures.groupby("month")["temperature"].count().to_dict()

        # Compute the heat demand (in MW) for each hour.
        def compute_hourly_demand_MW(hour):
            month = hour["month"]
            hourly_baseload = monthly_baseloads[month] / hours_per_month[month]
            hourly_demand_TJ = hourly_baseload + slope_TJ_per_degree_hour * hour["degree_hours"]
            hourly_demand_MW = (hourly_demand_TJ * 1_000_000) / 3600
            return round(hourly_demand_MW, 1)

        return current_temperatures.apply(compute_hourly_demand_MW, axis=1)

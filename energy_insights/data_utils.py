""" Shared code for data manipulation. """

import numpy as np
import pandas as pd

from .params_library.load_factors import LoadFactors

DAYS_IN_YEAR = 365


def _hourly_cooling_factor(hour: np.ndarray) -> np.ndarray:
    # Center peak cooling around 1 pm.
    peak_hour = 13
    # Demand in the bottom hour (relative to the peak of 1).
    low = .2

    a = .5 * (1 + low)
    b = .5 * (1 - low)
    x = (hour - peak_hour) / 24
    return a + b * np.cos(x * 2 * np.pi)


def _generate_heat_pump_series(index: pd.DatetimeIndex, cooling_twh: float, heating_twh: float) -> pd.Series:
    day = np.array(index.day_of_year)
    hour = np.array(index.hour)

    # Use a simple sine wave to continously switch between cooling (-1)
    # and heating (+1) mode depending on the day of year.
    mode_curve = np.cos(day / DAYS_IN_YEAR * 2 * np.pi)

    # Flip the sign so that both series are non-negative.
    cooling = -1 * _hourly_cooling_factor(hour) * mode_curve.clip(max=0)
    # Heating demand is assumed constant throught the day.
    heating = 1 * mode_curve.clip(min=0)

    cooling_scaled = cooling * cooling_twh / cooling.sum()
    heating_scaled = heating * heating_twh / heating.sum()

    return pd.Series(cooling_scaled + heating_scaled, index=index)


def scale_by_seasonal_factors(series: pd.Series, factors: LoadFactors) \
        -> tuple[pd.Series, pd.Series]:
    """
    Scales values in `series` by seasonal multiplication factors.

    Arguments:
        series: A power demand series to scale, must have numeric
            values and a Datetime index.
        factors: Dictionary of factors for scaling the baseload,
            heating and cooling loads.

    Returns:
        Pair with first entry being the modified baseload series and
        the second being the modified heat pump demand series.
    """
    hp_share_reference, hp_share_target = factors["heat_pumps_share"]
    cooling_share_reference, cooling_share_target = factors["heat_pumps_cooling_share"]

    # Compute synthetic cooling & heating series with given amount
    # in reference year.
    heat_pump_demand_reference = series.sum() * hp_share_reference
    cooling_twh_reference = heat_pump_demand_reference * cooling_share_reference
    heat_pumps_reference = _generate_heat_pump_series(
        index=series.index,
        cooling_twh=cooling_twh_reference,
        heating_twh=heat_pump_demand_reference - cooling_twh_reference
    )

    # Subtract synthetic cooling & heating from reference hourly load.
    baseload_reference = series - heat_pumps_reference

    # Inflate remaining load by a given factor (hour-by-hour).
    baseload_target = baseload_reference * factors["load_base"]

    # Compute synthetic cooling & heating series with given amounts for
    # target year.
    heat_pump_demand_target = baseload_target.sum() * hp_share_target / (1 - hp_share_target)
    cooling_twh_target = heat_pump_demand_target * cooling_share_target
    heat_pumps_target = _generate_heat_pump_series(
        index=series.index,
        cooling_twh=cooling_twh_target,
        heating_twh=heat_pump_demand_target - cooling_twh_target
    )

    return baseload_target, heat_pumps_target


"""
Provides power load factors for the grid.
"""

from typing import Optional, TypedDict

import pandas

from ..logging import get_logger
from ..region import Region, CZECHIA
from .storage import ember_ng_get_vehicle_types_consumption_gwh

logger = get_logger(__name__)

# Assuming 6% loss in transmission / distribution in CZ.
# Do not mess with other countries as the calibration is done.
__czech_transmission_distribution_loss_ratio = 0.06


class LoadFactors(TypedDict):
    load_base: float
    """Inflation factor for power demand other than EVs and heat pumps."""
    load_evs: float
    """Inflation factor for power demand for EV charging."""
    load_hps: float
    """Inflation factor for power demand for residential heat pumps."""


def _get_ratio_heat_pumps_cooling(
    df_tyndp_demand: pandas.DataFrame, tyndp_scenario_and_year: str, country: Region
) -> float:
    if country not in df_tyndp_demand["COUNTRY"].unique():
        logger.warning(
            f"Country {country} not present in the TYNDP dataset, returning heating==cooling"
        )
        return 0.5

    df_tyndp = df_tyndp_demand[
        (df_tyndp_demand["COUNTRY"] == country)
        & (df_tyndp_demand["ENERGY_CARRIER"] == "Electricity")
    ]

    df_tyndp_cooling = df_tyndp[df_tyndp["SUBSECTOR"] == "Cooling"]
    demand_cooling_twh = df_tyndp_cooling[tyndp_scenario_and_year].sum()
    df_tyndp_heating = df_tyndp[
        (df_tyndp["SUBSECTOR"] == "Space heating")
        | (df_tyndp["SUBSECTOR"] == "Space heating & hot water")
    ]
    demand_heating_twh = df_tyndp_heating[tyndp_scenario_and_year].sum()
    ratio_cooling = demand_cooling_twh / (demand_cooling_twh + demand_heating_twh)
    return ratio_cooling


def load_load_factors_from_ember_ng(
    df: pandas.DataFrame,
    df_tyndp_demand: pandas.DataFrame,
    base_country_demand_gwh: float,
    scenario: str,
    tyndp_base_scenario_and_year: str,
    tyndp_target_scenario_and_year: str,
    base_year: int,
    target_year: int,
    country: Region,
) -> LoadFactors:
    """
    Load power demand/load factors from the Ember New Generation [1]
    raw data file. It uses the TYNDP Demand input data file [2] to get
    separate cooling and heating demand figures for individual
    countries. Ratio of heating and cooling is used to split heat pump
    demand in the Ember data set. This in turn influences load factors
    for cooling (in summer) and heating (in winter).

    Arguments:
        df: Pandas data frame of the Ember New Generation dataset.
        df_tyndp_demand: Pandas data frame of the TYNDP demand input
            dataset.
        scenario: Name of scenario to load.
        tyndp_base_scenario_and_year: Name of the tyndp base scenario
            to use (the name also includes the base year).
        tyndp_target_scenario_and_year: Name of the tyndp target
            scenario to use (the name also includes the target year).
        base_year: Base year for load factors. Available years range
            between 2020 and 2050 in 5-year increments.
        target_year: Target year for load factors. Available years
            range between 2020 and 2050 in 5-year increments.
        country: Code of country whose load factors should be
            retrieved.

    Returns:
        Dictionary of load factors.

    [1]: https://ember-climate.org/insights/research/new-generation/
    [2]: https://2024.entsos-tyndp-scenarios.eu/download/
    """
    # Validate arguments.
    if country not in df["Country"].unique():
        raise ValueError(
            f"Country ‘{country}’ not available in Ember New Generation dataset"
        )
    if scenario not in df["Scenario"].unique():
        raise ValueError(f"Invalid Ember New Generation scenario ‘{scenario}’")
    if target_year not in df["Trajectory year"].unique():
        raise ValueError(f"Invalid Ember New Generation target year ‘{target_year}’")

    df = df[(df["Scenario"] == scenario) & (df["Country"] == country)]
    df_demand = df[(df["KPI"] == "Power demand") & (df["Technology"] != "Electrolysis")]

    def _compute_heating_cooling_demand(
        year: int,
        tyndp_scenario_and_year: str,
        remove_smart_charging: bool,
        scale_to_gwh: Optional[float] = None,
    ) -> tuple[float, float, float]:
        demand_total_w_o_losses = df_demand[df_demand["Trajectory year"] == year][
            "Result"
        ].sum()
        if country == CZECHIA:
            demand_total = demand_total_w_o_losses * (
                1 + __czech_transmission_distribution_loss_ratio
            )
        else:
            demand_total = demand_total_w_o_losses
        scaling_factor = 1 if scale_to_gwh is None else scale_to_gwh / demand_total

        # Subtract smart charging consumption so that this is not double-counted.
        if remove_smart_charging:
            _, smart_charging_consumption_gwh, _ = (
                ember_ng_get_vehicle_types_consumption_gwh(
                    df[df["Trajectory year"] == year]
                )
            )
            demand_total -= smart_charging_consumption_gwh

        demand_heat_pumps = df_demand[
            (df_demand["Trajectory year"] == year)
            & (df_demand["Technology"] == "Heat Pump")
        ]["Result"].sum()
        demand_other = demand_total - demand_heat_pumps
        demand_other_scaled = demand_other * scaling_factor

        heat_pumps_share = demand_heat_pumps / demand_total
        ratio_heat_pumps_cooling = _get_ratio_heat_pumps_cooling(
            df_tyndp_demand, tyndp_scenario_and_year, country
        )

        return demand_other_scaled, heat_pumps_share, ratio_heat_pumps_cooling

    demand_base_other, hp_share_base, hp_cooling_base = _compute_heating_cooling_demand(
        base_year,
        tyndp_base_scenario_and_year,
        remove_smart_charging=False,
        scale_to_gwh=base_country_demand_gwh,
    )
    demand_target_other, hp_share_target, hp_cooling_target = (
        _compute_heating_cooling_demand(
            target_year, tyndp_target_scenario_and_year, remove_smart_charging=True
        )
    )

    load_factor_base = demand_target_other / demand_base_other

    return {
        "heat_pumps_cooling_share": (hp_cooling_base, hp_cooling_target),
        "heat_pumps_share": (hp_share_base, hp_share_target),
        "load_base": load_factor_base,
    }

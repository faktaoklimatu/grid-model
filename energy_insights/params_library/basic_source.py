"""
Provides a library of production parameters for basic power sources.

Import this module to make the bundled parameter set available for loading.
"""

from typing import Optional

import pandas

from ..region import Region
# TODO: Avoid private access.
from ..sources.basic_source import BasicSourceType, _basic_sources, basic_source_defaults
from ..sources.economics import usd_to_eur_2022


# https://oenergetice.cz/jaderne-elektrarny/temelin-obnovil-povoleni-muze-na-zadost-ceps-snizit-vykon.
__JETE_flexibility_mw = 140
__flexible_nuclear_min_output_ratio = 0.3

# Order of basic sources in each scenario does not have to be alphabetical. It determines their
# order in the supplementary graphs and thus can follow the logic of the model (e.g. nuclear-centric
# modelling can deliberately put NUCLEAR first whereas RES-centric modelling will put RES first).
# TODO: Find a way not to repeat the same numbers all the time (e.g. current HYDRO capacity) and not
# to replicate the numbers from the `installed` module.
_basic_sources.update({
    "default": basic_source_defaults,
    "cz-2021": {
        BasicSourceType.SOLAR: {"capacity_mw": 2_066},
        BasicSourceType.ONSHORE: {"capacity_mw": 335},
        BasicSourceType.NUCLEAR: {
            "capacity_mw": 4_047,
            "max_decrease_mw": __JETE_flexibility_mw,
        },
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2.6GW-flexible-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_792},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_651},
        BasicSourceType.NUCLEAR: {
            "capacity_mw": 6_560,
            "max_decrease_mw": __JETE_flexibility_mw + 2600 * (1 - __flexible_nuclear_min_output_ratio),
        },
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-3.2GW-flexible-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_792},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_651},
        BasicSourceType.NUCLEAR: {
            "capacity_mw": 6_560,
            "max_decrease_mw": __JETE_flexibility_mw + 3200 * (1 - __flexible_nuclear_min_output_ratio),
        },
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-4GW-flexible-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_792},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_651},
        BasicSourceType.NUCLEAR: {
            "capacity_mw": 6_560,
            "max_decrease_mw": __JETE_flexibility_mw + 4000 * (1 - __flexible_nuclear_min_output_ratio),
        },
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },

    # Configs transferred from the `factors` module.
    # These are `capacity_mw` only.
    # TODO: What to do about the existing capacities (the default factor=1)?

    # A couple of scenarios for 2030 in CZ.
    "cz-2030-basic": {
        BasicSourceType.SOLAR: {"capacity_mw": 10_580},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_000},
        BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2030-advanced": {
        BasicSourceType.SOLAR: {"capacity_mw": 17_070},
        BasicSourceType.ONSHORE: {"capacity_mw": 2_700},
        BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2030-small-wind-boom": {
        BasicSourceType.SOLAR: {"capacity_mw": 12_400},
        BasicSourceType.ONSHORE: {"capacity_mw": 3_000},
        BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2030-wind-boom": {
        BasicSourceType.SOLAR: {"capacity_mw": 12_400},
        BasicSourceType.ONSHORE: {"capacity_mw": 5_000},
        BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2030-small-further-solar-growth": {
        BasicSourceType.SOLAR: {"capacity_mw": 16_500},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_000},
        BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2030-further-solar-growth": {
        BasicSourceType.SOLAR: {"capacity_mw": 20_700},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_000},
        BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2030-wind-and-solar-boom": {
        BasicSourceType.SOLAR: {"capacity_mw": 20_700},
        BasicSourceType.ONSHORE: {"capacity_mw": 5_000},
        BasicSourceType.NUCLEAR: {"capacity_mw": 4_047},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },

    # explainer scenarios:
    "cz-2050-explainer-biomass-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 23_650},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_122},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-explainer-hydrogen-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 57_400},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_122},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-explainer-hydrogen-scenario-optimised-solar": {
        BasicSourceType.SOLAR: {"capacity_mw": 28_700},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_122},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-explainer-import-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 17_280},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_122},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "de-2050-explainer-import-scenario-offshore": {
        BasicSourceType.SOLAR: {"capacity_mw": 0},
        BasicSourceType.ONSHORE: {"capacity_mw": 0},
        BasicSourceType.OFFSHORE: {"capacity_mw": 8_065},
        BasicSourceType.NUCLEAR: {"capacity_mw": 0},
        BasicSourceType.HYDRO: {"capacity_mw": 0},
    },
    "cz-2050-explainer-nuclear-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 9_460},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 6_560},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-explainer-optimisation-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 57_390},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 6_560},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },

    "cz-2050-little-wind-no-new-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 41_320},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_680},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_024},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-little-wind-1-new-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 35_120},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_680},
        BasicSourceType.NUCLEAR: {"capacity_mw": 3_338},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-little-wind-3-new-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_800},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_680},
        BasicSourceType.NUCLEAR: {"capacity_mw": 5_868},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },

    "cz-2050-little-VRE-no-new-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 16_530},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_680},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_024},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-little-VRE-1-new-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 12_400},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_680},
        BasicSourceType.NUCLEAR: {"capacity_mw": 3_338},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-little-VRE-3-new-nuclear": {
        BasicSourceType.SOLAR: {"capacity_mw": 8_260},
        BasicSourceType.ONSHORE: {"capacity_mw": 1_680},
        BasicSourceType.NUCLEAR: {"capacity_mw": 5_868},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },

    # Scenarios for CZ energy strategy modelling.
    "cz-2050-SEK-low-load-low-nuclear-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_800},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 6_560},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-SEK-low-load-low-nuclear-2.6GW-flexible-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_800},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {
            "capacity_mw": 6_560,
            "max_decrease_mw": __JETE_flexibility_mw + 2_600 * (1 - __flexible_nuclear_min_output_ratio),
        },
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-SEK-low-load-extreme-nuclear-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 16_530},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 7_285},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-SEK-mid-load-extreme-nuclear-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_800},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {"capacity_mw": 8_094},
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },
    "cz-2050-SEK-mid-load-extreme-nuclear-4GW-flexible-scenario": {
        BasicSourceType.SOLAR: {"capacity_mw": 24_800},
        BasicSourceType.ONSHORE: {"capacity_mw": 14_650},
        BasicSourceType.NUCLEAR: {
            "capacity_mw": 8_094,
            "max_decrease_mw": __JETE_flexibility_mw + 4_000 * (1 - __flexible_nuclear_min_output_ratio),
        },
        BasicSourceType.HYDRO: {"capacity_mw": 1_105},
    },

    # CEE plans for 2030.
    # Austria
    # https://www.iea.org/policies/12401-austrian-recovery-resilience-plan-1sustainable-construction-climate-neutral-transformation-renewable-expansion-act
    "at-2030": {
        BasicSourceType.SOLAR: {"capacity_mw": 13_000},
        BasicSourceType.ONSHORE: {"capacity_mw": 8_000},
        BasicSourceType.HYDRO: {"capacity_mw": 9_600},
    },
    "at-2030-potential": {
        BasicSourceType.SOLAR: {"capacity_mw": 16_000},
        BasicSourceType.ONSHORE: {"capacity_mw": 9_600},
        BasicSourceType.HYDRO: {"capacity_mw": 10_000},
    },
    # Germany
    # It's hard to find an authoritative source, the numbers here are inspired by:
    # https://reneweconomy.com.au/germany-plans-32gw-of-new-wind-and-solar-a-year-to-meet-2030-renewables-target/
    "de-2030-government-plans-achieved": {
        BasicSourceType.SOLAR: {"capacity_mw": 193_600},
        BasicSourceType.ONSHORE: {"capacity_mw": 109_700},
        BasicSourceType.OFFSHORE: {"capacity_mw": 30_200},
        BasicSourceType.HYDRO: {"capacity_mw": 4_937},
    },
    "de-2030-government-plans-underachieved": {
        BasicSourceType.SOLAR: {"capacity_mw": 162_200},
        BasicSourceType.ONSHORE: {"capacity_mw": 82_300},
        BasicSourceType.OFFSHORE: {"capacity_mw": 23_200},
        BasicSourceType.HYDRO: {"capacity_mw": 4_937},
    },
    "de-2030-government-plans-overachieved": {
        BasicSourceType.SOLAR: {"capacity_mw": 216_300},
        BasicSourceType.ONSHORE: {"capacity_mw": 137_100},
        BasicSourceType.OFFSHORE: {"capacity_mw": 38_700},
        BasicSourceType.HYDRO: {"capacity_mw": 4_937},
    },
    "de-2030-potential": {
        BasicSourceType.SOLAR: {"capacity_mw": 243_300},
        BasicSourceType.ONSHORE: {"capacity_mw": 164_500},
        BasicSourceType.OFFSHORE: {"capacity_mw": 42_600},
        BasicSourceType.HYDRO: {"capacity_mw": 4_937},
    },
    # Poland
    # https://www.gov.pl/web/climate/energy-policy-of-poland-until-2040-epp2040
    "pl-2030": {
        BasicSourceType.SOLAR: {"capacity_mw": 17_000 * 1.2},
        # This is a hack to model 3.8 GW of offshore wind that produces
        # ~16.6 TWh and 9.6 GW of onshore wind that produces
        # ~21 TWh. The ENTSO-E data has 0 for offshore production, so
        # instead we specify onshore only. Both values are increased by
        # a factor of 1.2 based on the planned update of the energy policy.
        # TODO: Remove hack once we have fallbacks for missing data.
        BasicSourceType.ONSHORE: {"capacity_mw": 16_400 * 1.2},
        BasicSourceType.HYDRO: {"capacity_mw": 780},
    },
    "pl-2030-potential": {
        BasicSourceType.SOLAR: {"capacity_mw": 17_000 * 1.5},
        # Same hack as above. Both values are increased by a factor of
        # 1.5 based on the planned update of the energy policy + potential
        # buffer.
        # TODO: Remove hack once we have fallbacks for missing data.
        BasicSourceType.ONSHORE: {"capacity_mw": 16_400 * 1.5},
        BasicSourceType.HYDRO: {"capacity_mw": 780},
    },
    # Slovakia
    # Slovak NECP is completely bogus, with basically no growth of RES share until 2030.
    # https://energy.ec.europa.eu/system/files/2022-08/sk_final_necp_main_sk.pdf
    # Assuming a bit of good will after the gas crisis, boosting solar to 2x. There was no wind in
    # 2020, so there is no data to boost.
    # TODO: Add fallback for wind once we support fallbacks.
    "sk-2030": {
        BasicSourceType.SOLAR: {"capacity_mw": 1_100},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_000},
        BasicSourceType.HYDRO: {"capacity_mw": 1_630},
    },
    "sk-2030-potential": {
        BasicSourceType.SOLAR: {"capacity_mw": 2_100},
        BasicSourceType.NUCLEAR: {"capacity_mw": 2_000},
        BasicSourceType.HYDRO: {"capacity_mw": 1_630},
    },
})


# Mapping between our basic sources types and values in the
# "Technology - Grouped" column from the Ember NG dataset.
# NOTE: The order of items in this dict effectively determines the
# order in which the sources are plotted in model summary plots.
__ember_ng_technologies_map: dict[str, BasicSourceType] = {
    "Solar": BasicSourceType.SOLAR,
    "Onshore wind": BasicSourceType.ONSHORE,
    "Offshore wind": BasicSourceType.OFFSHORE,
    "Nuclear": BasicSourceType.NUCLEAR,
    "Hydropower": BasicSourceType.HYDRO,
}


def load_basic_sources_from_ember_ng(
        df: pandas.DataFrame,
        scenario: str,
        year: int,
        country: Region,
        allow_capex_optimization_against_base_year: Optional[int],
        load_hydro: bool) -> dict[BasicSourceType, dict]:
    """
    Load basic source capacities from Ember New Generation [1] raw
    data file.

    Arguments:
        df: Pandas data frame of the Ember New Generation dataset.
        scenario: Name of scenario to load.
        year: Target year for basic capacities. Available years range
            between 2020 and 2050 in 5-year increments.
        country: Code of country whose basic capacities should be
            loaded.

    Returns:
        Collection of dictionaries specifying the requested basic
        sources from Ember NG.

    [1]: https://ember-climate.org/insights/research/new-generation/
    """
    # Validate arguments.
    if country not in df["Country"].unique():
        raise ValueError(f"Country ‘{country}’ not available in Ember New Generation dataset")
    if scenario not in df["Scenario"].unique():
        raise ValueError(f"Invalid Ember New Generation scenario ‘{scenario}’")
    if year not in df["Trajectory year"].unique():
        raise ValueError(f"Invalid Ember New Generation target year ‘{year}’")

    df_target = df[(df["KPI"] == "Installed capacities - power generation") &
                   (df["Scenario"] == scenario) &
                   (df["Trajectory year"] == year) &
                   (df["Country"] == country)]

    sources: dict[BasicSourceType, dict] = {}

    df_base: Optional[pandas.DataFrame] = None
    if allow_capex_optimization_against_base_year is not None:
        base_year = allow_capex_optimization_against_base_year
        df_base = df[(df["KPI"] == "Installed capacities - power generation") &
                     (df["Scenario"] == scenario) &
                     (df["Trajectory year"] == base_year) &
                     (df["Country"] == country)]

    for ember_technology, source_type in __ember_ng_technologies_map.items():
        if not load_hydro and source_type == BasicSourceType.HYDRO:
            continue

        matched_target = df_target[df_target["Technology - Grouped"] == ember_technology]
        installed_mw: float = 0
        if not matched_target.empty:
            target_mw: float = 1000 * matched_target["Result"].sum()
            # Treat sources below 100 kW as 0.
            if target_mw > 0.1:
                installed_mw = target_mw

        # Use the base installed capacity as the minimum for capex optimization (especially needed
        # for Hydro which is expensive to build and mostly already built).
        min_installed_mw = installed_mw
        if df_base is not None:
            matched_base = df_base[df_base["Technology - Grouped"] == ember_technology]
            if not matched_base.empty:
                base_installed_mw = 1000 * matched_base["Result"].sum()
                min_installed_mw = min(min_installed_mw, base_installed_mw)

        sources[source_type] = get_cost_estimates_2030(source_type) | {
            "capacity_mw": installed_mw,
            "min_capacity_mw": min_installed_mw,
        }

    return sources


def get_cost_estimates_2030(type: BasicSourceType) -> dict:
    """
    Return 2030 cost estimates, in EUR_2022, based on IEA's World Energy Outlook 2023 for Europe
    for the (mid-ambition) Announced Pledges Scenario.
    https://iea.blob.core.windows.net/assets/2b0ded44-6a47-495b-96d9-2fac0ac735a8/WorldEnergyOutlook2023.pdf
    """
    if type == BasicSourceType.NUCLEAR:
        # Most nuclear contracts need to be signed now, assume current cost estimate for NOAK (this
        # is already optimistic as it is not clear Czech blocks will not suffer from FOAK effects).
        return {}
    if type == BasicSourceType.SOLAR:
        return {"overnight_costs_per_kw_eur": usd_to_eur_2022(600)}
    if type == BasicSourceType.ONSHORE:
        return {"overnight_costs_per_kw_eur": usd_to_eur_2022(1650)}
    if type == BasicSourceType.OFFSHORE:
        return {
            "overnight_costs_per_kw_eur": usd_to_eur_2022(2200),
            "fixed_o_m_costs_per_kw_eur": usd_to_eur_2022(50),
        }
    return {}

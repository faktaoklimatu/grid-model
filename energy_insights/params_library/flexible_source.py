"""
Provides a library of capacity parameters for flexible power sources.

Import this module to make the bundled parameter set available for loading.
"""

import pandas

from ..region import Region
from ..sources.economics import usd_to_eur_2022
# TODO: Avoid private access.
from ..sources.flexible_source import FlexibleSourceType, _flexible_sources
from ..sources.heat_source import ExtractionTurbine

# Order of flexible sources in each scenario does not have to be alphabetical. It determines their
# order in the supplementary graphs and thus can follow the logic of the model (e.g. biomass-centric
# modelling can deliberately put all biomass first whereas CCS-centric modelling will put CCS
# first).
_flexible_sources.update({
    "cz-2050-hydrogen": {
        FlexibleSourceType.GAS_CCGT_CCS: {
            'capacity_mw': 1_500
        },
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 2_500,
            'max_total_twh': 11,
        },
        FlexibleSourceType.BIOGAS_PEAK: {
            'capacity_mw': 2_000,
            'max_total_twh': 1,
        },
    },
    "cz-2050-nuclear": {
        FlexibleSourceType.GAS_CCGT_CCS: {
            'capacity_mw': 2_000
        },
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 2_500,
            'max_total_twh': 8,
        },
        FlexibleSourceType.BIOGAS_PEAK: {
            'capacity_mw': 5_000,
            'max_total_twh': 3,
        },
    },
    "cz-2050-import": {
        FlexibleSourceType.GAS_CCGT_CCS: {
            'capacity_mw': 2_000,
        },
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 3_000,
            'max_total_twh': 8,
        },
        FlexibleSourceType.BIOGAS_PEAK: {
            'capacity_mw': 6_000,
            'max_total_twh': 3,
        },
    },
    "cz-2050-SEK-low-load-low-nuclear": {
        FlexibleSourceType.GAS_CCGT_CCS: {
            'capacity_mw': 2_000
        },
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 2_500,
            'max_total_twh': 8,
        },
        FlexibleSourceType.BIOGAS_PEAK: {
            'capacity_mw': 5_000,
            'max_total_twh': 3,
        },
    },
    "cz-2050-SEK-low-load-extreme-nuclear": {
        FlexibleSourceType.GAS_CCGT_CCS: {
            'capacity_mw': 2_000
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 1_000
        },
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 2_500,
            'max_total_twh': 8,
        },
        FlexibleSourceType.BIOGAS_PEAK: {
            'capacity_mw': 5_000,
            'max_total_twh': 3,
        },
    },
    "cz-2050-SEK-mid-load-extreme-nuclear": {
        FlexibleSourceType.GAS_CCGT_CCS: {
            'capacity_mw': 2_000
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 3_000
        },
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 2_500,
            'max_total_twh': 8,
        },
        FlexibleSourceType.BIOGAS_PEAK: {
            'capacity_mw': 5_000,
            'max_total_twh': 3,
        },
    },
    "cz-2030-basic": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 800,
            'max_total_twh': 4.2,
        },
        FlexibleSourceType.BIOGAS: {
            'capacity_mw': 323 * 0.3,
            'max_total_twh': 2.5 * 0.3,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 4_000,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 700,
        },
        FlexibleSourceType.WASTE: {
            'capacity_mw': 60,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 2_400,
        },
        FlexibleSourceType.GAS_ENGINE: {
            'capacity_mw': 600,
        },
    },
    "cz-2030-advanced": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 1_000,
            'max_total_twh': 5.1,
        },
        FlexibleSourceType.BIOGAS: {
            'capacity_mw': 323 * 0.2,
            'max_total_twh': 2.5 * 0.2,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 4_000,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 700,
        },
        FlexibleSourceType.WASTE: {
            'capacity_mw': 80,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 2_800,
        },
        FlexibleSourceType.GAS_ENGINE: {
            'capacity_mw': 600,
        },
    },
    "cz-2030-potential": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 2_000,
            'max_total_twh': 10,
            'min_capacity_mw': 700,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 3_000,
            'min_capacity_mw': 3_000,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 500,
            'min_capacity_mw': 500,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 4_000,
            'min_capacity_mw': 3_000,
        },
    },
    "cz-current": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 500,  # This somehow takes into account co-burning in coal capacities.
            'max_total_twh': 2.5,
        },
        FlexibleSourceType.BIOGAS: {
            'capacity_mw': 323,
            'max_total_twh': 2.5,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 6_222,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 1_000,
        },
        FlexibleSourceType.WASTE: {
            'capacity_mw': 30,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 1_339,
        },
        FlexibleSourceType.GAS_ENGINE: {
            'capacity_mw': 927,
        },
    },
    "cz-current-heat": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 500,  # This somehow takes into account co-burning in coal capacities.
            'max_total_twh': 2.5,
            'extraction_turbine': ExtractionTurbine.canonical(),
        },
        FlexibleSourceType.BIOGAS: {
            'capacity_mw': 323,
            'max_total_twh': 2.5,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 3_882,
        },
        FlexibleSourceType.LIGNITE_BACKPRESSURE: {
            'capacity_mw': 611,
        },
        FlexibleSourceType.LIGNITE_EXTRACTION: {
            'capacity_mw': 2_619,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 849,
        },
        FlexibleSourceType.COAL_BACKPRESSURE: {
            'capacity_mw': 214,
        },
        FlexibleSourceType.COAL_EXTRACTION: {
            'capacity_mw': 522,
        },
        FlexibleSourceType.WASTE: {
            'capacity_mw': 30,
            # Simplification, is almost irrelevant.
            'extraction_turbine': ExtractionTurbine.canonical(),
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 1_339,
        },
        FlexibleSourceType.GAS_ENGINE: {
            'capacity_mw': 927,
        },
    },
    "de-current": {
        FlexibleSourceType.SOLID_BIOMASS: {
            # 9.5 GW in DE artificially decreased to model export to FR etc.
            'capacity_mw': 4_500,
            'max_total_twh': 50,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 18_900,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 19_000,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 32_000,
        },
    },
    # Based on German NECP (2019) with decreased coal. 100 % of coal speculatively replaced by new
    # gas (2/3 ocgt, 1/3 ccgt). This still means decreasing relative capacity as load increases
    # significantly.
    "de-2030": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 6_129,
            'max_total_twh': 70,
        },
        # Capacities in coal to allow following phase-out:
        # https://www.cleanenergywire.org/factsheets/spelling-out-coal-phase-out-germanys-exit-law-draft.
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 9_000,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 8_000,
        },
        FlexibleSourceType.GAS_PEAK: {
            'capacity_mw': 14_000,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 39_000,
        },
    },
    "de-2030-potential": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 10_000,
            'max_total_twh': 10,
            'min_capacity_mw': 700,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 9_000,
            'min_capacity_mw': 9_000,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 8_000,
            'min_capacity_mw': 8_000,
        },
        FlexibleSourceType.GAS_PEAK: {
            'capacity_mw': 20_000,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 50_000,
            'min_capacity_mw': 32_000,
        },
    },
    "pl-current": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 660,
            'max_total_twh': 5,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 7_560,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 19_000,
        },
        FlexibleSourceType.MAZUT: {
            'capacity_mw': 400,
        },
        FlexibleSourceType.GAS_CCGT: {  # Roughly corresponds to 3.79 fossil gas + 0.28 coal-derived gas.
            'capacity_mw': 4_000,
        },
    },
    "pl-2030": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 1_500,
            'max_total_twh': 6,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 7_560,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 19_000,
        },
        FlexibleSourceType.GAS_CCGT: {  # Roughly corresponds to 3.79 fossil gas + 0.28 coal-derived gas.
            'capacity_mw': 4_000,
        },
    },
    "pl-2030-potential": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 3_000,
            'min_capacity_mw': 660,
            'max_total_twh': 15,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 7_560,
            'min_capacity_mw': 7_560,
        },
        FlexibleSourceType.COAL: {
            'capacity_mw': 19_000,
            'min_capacity_mw': 19_000,
        },
        FlexibleSourceType.MAZUT: {
            'capacity_mw': 400,
        },
        FlexibleSourceType.GAS_CCGT: {  # Roughly corresponds to 3.79 fossil gas + 0.28 coal-derived gas.
            'capacity_mw': 6_000,
            'min_capacity_mw': 4_000,
        },
    },
    "at-current": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 480,
            'max_total_twh': 5,
        },
        FlexibleSourceType.MAZUT: {
            'capacity_mw': 120,
        },
        FlexibleSourceType.GAS_PEAK: {
            # Ca. from a quick Wikipedia search.
            'capacity_mw': 400,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 3_810,
        },
    },
    "at-2030": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 1_500,
            'max_total_twh': 5,
        },
        FlexibleSourceType.GAS_PEAK: {
            'capacity_mw': 1_000,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 3_810,
        },
    },
    "at-2030-potential": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 2_000,
            'min_capacity_mw': 480,
            'max_total_twh': 10,
        },
        FlexibleSourceType.GAS_PEAK: {
            'capacity_mw': 2_000,
            'min_capacity_mw': 400,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 6_000,
            'min_capacity_mw': 3_810,
        },
    },
    "sk-current": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 230,
            'max_total_twh': 2,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 280,
        },
        FlexibleSourceType.MAZUT: {
            'capacity_mw': 260,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 1_180,
        },
    },
    "sk-2030": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 500,
            'max_total_twh': 3,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 280,
        },
        FlexibleSourceType.MAZUT: {
            'capacity_mw': 260,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 1_180,
        },
    },
    "sk-2030-potential": {
        FlexibleSourceType.SOLID_BIOMASS: {
            'capacity_mw': 1_000,
            'min_capacity_mw': 230,
            'max_total_twh': 4,
        },
        FlexibleSourceType.LIGNITE: {
            'capacity_mw': 280,
            'min_capacity_mw': 280,
        },
        FlexibleSourceType.MAZUT: {
            'capacity_mw': 260,
            'min_capacity_mw': 260,
        },
        FlexibleSourceType.GAS_CCGT: {
            'capacity_mw': 2_000,
            'min_capacity_mw': 1_180,
        },
    },
})


# 2030 cost estimates from Ember's New Generation report.
# https://ember-climate.org/app/uploads/2022/06/Technical-Report-New-Generation.pdf for
__ember_ng_sources_map: dict[str, tuple[FlexibleSourceType, dict]] = {
    # FIXME: Temporary workaround for the inability to specify
    # parameters granularly when loading from Ember NG.
    # See `load_flexible_sources_from_ember_ng()` below.
    "Biomass fleet": (FlexibleSourceType.SOLID_BIOMASS_CHP,
                      # Take an upper price for biomass tech (anyway excluded from optimisation).
                      {"overnight_costs_per_kw_eur": 3000}),
    "Biomass CHP": (FlexibleSourceType.SOLID_BIOMASS_CHP, {"overnight_costs_per_kw_eur": 3000}),
    # TODO: Report says "marine, geothermal, renewable waste". In Czech context, this must be mostly
    # biogas, so lump into biomass CHP.
    "Other renewable fleet": (FlexibleSourceType.SOLID_BIOMASS_CHP,
                              {"overnight_costs_per_kw_eur": 3000}),
    # Assume Lazard's current estimate and apply minor scaling effect.
    "CCGT CCS fleet": (FlexibleSourceType.GAS_CCGT_CCS,
                       {"overnight_costs_per_kw_eur":  usd_to_eur_2022(2000)}),
    # Ember prices are incredible for following sources, take our defaults.
    "CCGT fleet": (FlexibleSourceType.GAS_CCGT, {}),
    "Coal fleet": (FlexibleSourceType.COAL, {}),
    "Lignite fleet": (FlexibleSourceType.LIGNITE, {}),
    "Lignite CHP": (FlexibleSourceType.LIGNITE_EXTRACTION, {}),
    # Central estimate for 2030 from Danish Energy Agency
    # https://ens.dk/en/our-services/projections-and-models/technology-data/technology-data-generation-electricity-and
    "OCGT fleet": (FlexibleSourceType.GAS_PEAK, {"overnight_costs_per_kw_eur": 470}),
    "Oil fleet": (FlexibleSourceType.FOSSIL_OIL, {}),
    "Gas CHP": (FlexibleSourceType.GAS_CHP, {}),
    "DSR fleet": (FlexibleSourceType.DSR, {}),
    "SMR fleet": (FlexibleSourceType.SMR, {}),
}


# TODO: It might be prudent to limit total production from some sources
# (e.g. biomass) using `max_total_twh` or `uptime_ratio`. How to go
# about specifying this in the new API?
def load_flexible_sources_from_ember_ng(df: pandas.DataFrame,
                                        scenario: str,
                                        year: int,
                                        country: Region,
                                        allow_capex_optimization: bool) -> dict[FlexibleSourceType, dict]:
    """
    Load flexible source capacities from Ember New Generation [1] raw
    data file.

    Arguments:
        df: Pandas data frame of the Ember New Generation dataset.
        scenario: Name of scenario to load.
        year: Target year for flexible capacities. Available years
            range between 2020 and 2050 in 5-year increments.
        country: Code of country whose flexible capacities should be
            loaded.

    Returns:
        Collection of dictionaries specifying the requested flexible
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

    df = df[(df["KPI"] == "Installed capacities - power generation") &
            (df["Scenario"] == scenario) &
            (df["Trajectory year"] == year) &
            (df["Country"] == country)]

    sources: dict[FlexibleSourceType, dict] = {}

    for ember_technology, (source_type, template) in __ember_ng_sources_map.items():
        matched = df[df["Technology"] == ember_technology].head(1)
        if matched.empty:
            continue
        installed_mw: float = 1000 * matched["Result"].item()
        # Ignore sources below 100 kW.
        if installed_mw < .1:
            continue
        min_installed_mw = 0 if allow_capex_optimization else installed_mw
        if source_type in sources:
            sources[source_type]["capacity_mw"] += installed_mw
            sources[source_type]["min_capacity_mw"] += min_installed_mw
        else:
            sources[source_type] = template | {
                "capacity_mw": installed_mw,
                "min_capacity_mw": min_installed_mw,
            }

    return sources

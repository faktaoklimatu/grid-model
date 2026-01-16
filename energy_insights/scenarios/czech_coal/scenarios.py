from copy import deepcopy
from typing import NotRequired, TypedDict

from ...sources.basic_source import BasicSourceType
from ...sources.flexible_source import FlexibleSourceType
from ...sources.reserves import FastReservesProvider
from ...sources.storage import StorageType

SourceType = BasicSourceType | FlexibleSourceType | StorageType


class ScenarioSpec(TypedDict):
    adjustments: dict[SourceType, dict]
    flexible_derating: NotRequired[float]
    global_adjustments: NotRequired[dict[SourceType, dict]]
    input_costs: NotRequired[str]
    interconnectors: NotRequired[dict[str, float | int]]
    post_eva: NotRequired[bool]
    target_year: int


def amend(original: ScenarioSpec, overrides: dict) -> ScenarioSpec:
    modified = deepcopy(original)

    for key, value in overrides.items():
        if isinstance(value, dict):
            modified[key] = amend(modified.get(key, {}), value)
        else:
            modified[key] = value

    return modified


# Maximum allowed annual capacity factor for biomass and biogas.
_bioenergy_max_capacity_factor = 0.8
# Maximum capacity factor for natural gas and coal (hard and lignite),
# respectively.
_fossil_gas_max_capacity_factor = 0.85
_coal_max_capacity_factor = 0.85
# Similarly for CHP variants.
_fossil_gas_chp_max_capacity_factor = 0.4
_coal_chp_max_capacity_factor = 0.4

_global_adjustments: dict[SourceType, dict] = {
    # Fossil coal sources.
    FlexibleSourceType.COAL: {
        "uptime_ratio": _coal_max_capacity_factor,
    },
    FlexibleSourceType.COAL_BACKPRESSURE: {
        "uptime_ratio": _coal_chp_max_capacity_factor,
    },
    FlexibleSourceType.COAL_EXTRACTION: {
        "uptime_ratio": _coal_chp_max_capacity_factor,
    },
    FlexibleSourceType.COAL_SUPERCRITICAL: {
        "uptime_ratio": _coal_max_capacity_factor,
    },
    FlexibleSourceType.LIGNITE: {
        "uptime_ratio": _coal_max_capacity_factor,
    },
    FlexibleSourceType.LIGNITE_BACKPRESSURE: {
        "uptime_ratio": _coal_chp_max_capacity_factor,
    },
    FlexibleSourceType.LIGNITE_EXTRACTION: {
        "uptime_ratio": _coal_chp_max_capacity_factor,
    },
    FlexibleSourceType.LIGNITE_OLD: {
        "uptime_ratio": _coal_max_capacity_factor,
    },
    FlexibleSourceType.LIGNITE_SUPERCRITICAL: {
        "uptime_ratio": _coal_max_capacity_factor,
    },
    # Fossil gas sources.
    FlexibleSourceType.GAS_CCGT: {
        "uptime_ratio": _fossil_gas_max_capacity_factor,
    },
    FlexibleSourceType.GAS_CHP: {
        "uptime_ratio": _fossil_gas_chp_max_capacity_factor,
    },
    FlexibleSourceType.GAS_PEAK: {
        "uptime_ratio": _fossil_gas_max_capacity_factor,
    },
    FlexibleSourceType.GAS_ENGINE: {
        "uptime_ratio": _fossil_gas_max_capacity_factor,
    },
    FlexibleSourceType.GAS_ENGINE_CHP: {
        "uptime_ratio": _fossil_gas_chp_max_capacity_factor,
    },
    # Bioenergy sources.
    FlexibleSourceType.BIOGAS: {
        "uptime_ratio": _bioenergy_max_capacity_factor,
    },
    FlexibleSourceType.SOLID_BIOMASS: {
        "uptime_ratio": _bioenergy_max_capacity_factor,
    },
    FlexibleSourceType.SOLID_BIOMASS_CHP: {
        "uptime_ratio": _bioenergy_max_capacity_factor,
    },
}

cz_coal_scenarios: dict[str, ScenarioSpec] = {}

# Current scenario hierarchy/inheritance:
#
#                ┌── 2028-base-plus
#   2028-base ←──┤
#                └── 2028-ex-seven ←── 2028-ex-seven-suas
#                                         ↑
#                                         └── 2028-stress
#
# NOTE: Installed capacities of (thermal) flexible sources (e.g. coal,
# gas and biomass capacities) entered here are considered gross and are
# be automatically derated to net capacities in the loader.
cz_coal_scenarios["2028-base"] = {
    "target_year": 2028,
    "global_adjustments": _global_adjustments,
    "adjustments": {
        BasicSourceType.ONSHORE: {"capacity_mw": 500},
        BasicSourceType.SOLAR: {"capacity_mw": 7000},
        FlexibleSourceType.BIOGAS: {
            "capacity_mw": 400,
            "reserves": None,
        },
        FlexibleSourceType.COAL: {"capacity_mw": 0},
        FlexibleSourceType.COAL_BACKPRESSURE: {"capacity_mw": 0},
        FlexibleSourceType.COAL_EXTRACTION: {"capacity_mw": 174},
        FlexibleSourceType.DSR: {"capacity_mw": 0},
        FlexibleSourceType.GAS_CCGT: {"capacity_mw": 840},
        FlexibleSourceType.GAS_CHP: {
            "capacity_mw": 1040,
            "reserves": FastReservesProvider(
                max_installed_fraction=0.6,
                min_dispatch_fraction=0.4,
            ),
        },
        FlexibleSourceType.GAS_ENGINE_CHP: {"capacity_mw": 475},
        FlexibleSourceType.GAS_PEAK: {"capacity_mw": 138},
        # Others + SUAS (Tisová & Vřesová).
        FlexibleSourceType.LIGNITE: {"capacity_mw": 1308 + 162},
        # Others + SUAS (Tisová & Vřesová).
        FlexibleSourceType.LIGNITE_BACKPRESSURE: {"capacity_mw": 530 + 13},
        # Others + Kladno + SUAS (Tisová & Vřesová).
        FlexibleSourceType.LIGNITE_EXTRACTION: {"capacity_mw": 1748 + 404 + 353},
        # Sev.en only (Chvaletice & Počerady).
        FlexibleSourceType.LIGNITE_OLD: {"capacity_mw": 1820},
        FlexibleSourceType.LIGNITE_SUPERCRITICAL: {"capacity_mw": 660},
        FlexibleSourceType.SOLID_BIOMASS: {"capacity_mw": 0},
        FlexibleSourceType.SOLID_BIOMASS_CHP: {"capacity_mw": 300},
        StorageType.LI: {"capacity_mw": 100, "max_energy_mwh": 200},
        StorageType.PUMPED: {"reserves": None},
        StorageType.PUMPED_OPEN: {"reserves": None},
        # StorageType.RESERVOIR: {"reserves": None},
    },
    # Reduce available capacity of dispatchable sources globally
    # by 15%. Applied in addition to net-capacity derating.
    "flexible_derating": 0.15,
    "interconnectors": {
        # Mid-2027 capacities, with Hradec–Roehrsdorf interconnection
        # shut down for maintenance.
        "CZ->DE": 1500,
        "DE->CZ": 1350,
    },
}

cz_coal_scenarios["2028-base-plus"] = amend(
    cz_coal_scenarios["2028-base"],
    {
        "interconnectors": {
            # Pre-2027 capacities, without Hradec–Roehrsdorf works.
            "CZ->DE": 2900,
            "DE->CZ": 2750,
        },
    },
)

cz_coal_scenarios["2028-ex-seven"] = amend(
    cz_coal_scenarios["2028-base"],
    {
        "adjustments": {
            # Kladno shuts down.
            FlexibleSourceType.LIGNITE_EXTRACTION: {"capacity_mw": 1748 + 353},
            # Chvaletice and Počerady (Sev.en) shut down.
            FlexibleSourceType.LIGNITE_OLD: {"capacity_mw": 0},
        }
    },
)

cz_coal_scenarios["2028-ex-seven-suas"] = amend(
    cz_coal_scenarios["2028-ex-seven"],
    {
        "adjustments": {
            # Tisová and Vřesová (SUAS) shut down.
            FlexibleSourceType.LIGNITE: {"capacity_mw": 1308},
            FlexibleSourceType.LIGNITE_BACKPRESSURE: {"capacity_mw": 530},
            FlexibleSourceType.LIGNITE_EXTRACTION: {"capacity_mw": 1748},
        }
    },
)

cz_coal_scenarios["2028-stress"] = amend(
    cz_coal_scenarios["2028-ex-seven-suas"],
    {
        "adjustments": {
            # Shut down approximately one block of Dukovany for the whole year.
            # BasicSourceType.NUCLEAR: {"capacity_mw": 4047 - 510},
            # NOTE: We want to decrease the output uniformly by 510 MW
            # rather than by approx. 12.6% which is what this would do.
            # The decrease is now handled in a very ugly way in
            # execution_utils.optimize_runs() instead.
        },
        # Decrease (or increase) capacities abroad per EVA results.
        "post_eva": True,
    },
)

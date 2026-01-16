"""
Provides params for interconnector capacities.
"""

from collections.abc import Collection
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from statistics import mean
from typing import Optional

import pandas

from .country_distances import get_transmission_distance_km
from ..region import *
from ..grid_capex_utils import get_interconnector_capex_per_year_eur

# Based on https://ember-climate.org/insights/research/new-generation/#supporting-material-downloads
__current_cz_de = 2100.0
__current_cz_at = 800.0
__2030_stated_cz_at_symmetric = 900.0
__2030_ambitious_cz_at_symmetric = 1900.0
__current_cz_sk = 1800.0
__current_cz_pl = 600.0

__current_de_cz = 1500.0
__current_de_pl = 500.0
__2030_stated_de_pl = 3500.0
__2030_ambitious_de_pl = 6500.0
__current_de_at_symmetric = 5000.0
__2030_stated_de_at_symmetric = 5400.0

__current_at_sk_symmetric = 0.0
__2030_ambitious_at_sk = 500.0
__current_at_cz = 900.0

__current_sk_pl_symmetric = 1000.0
__current_sk_cz = 1100.0

__current_pl_de = 2500.0
__2030_stated_pl_de = 3000.0
__2030_ambitious_pl_de = 7500.0
__current_pl_cz = 800.0

__generic_transmission_loss = .02

# Very rough estimates for 400kV double-circuit line. Losses are slightly sublinear in distance,
# simplify that by a base loss of 1% for each link and then linear 5.5% per each 1000 km.
# Figure from https://en.wikipedia.org/wiki/High-voltage_direct_current#Comparison_with_AC.
__AC_transmission_loss_base = 0.01
__AC_transmission_loss_per_1000_km = 0.055
# Same for HVDC (conversion losses, etc.), with lower variable part.
# Conversion loss rough estimate based on https://en.wikipedia.org/wiki/HVDC_converter
__HVDC_transmission_loss_base = 0.015
# Rough estimate from https://en.wikipedia.org/wiki/High-voltage_direct_current.
__HVDC_transmission_loss_per_1000_km = 0.035

# The actual cables can last this long. TSO may be incentivized to replace it sooner because of RAB,
# but we can ignore that as a regulatory bug. Furthermore the actual towers definitely can last
# longer so the investment to prolong the lifetime may be lower.
__interconnector_HVAC_lifetime_years = 50
# Middle estimate from Table 6 in
# https://www.e3s-conferences.org/articles/e3sconf/pdf/2022/17/e3sconf_eregce2022_02001.pdf.
__interconnector_HVDC_lifetime_years = 30
# Assuming a mix of subsidies and of the RAB model.
__interconnector_discount_rate = 1.04

# Investment and O&M costs.
# Rather assuming 50% higher costs than what literature review shows to be on the safe side (the
# costs are anyway low).
# We need higher rated capacity to get the desired net transfer capacity (NTC), increase investment
# costs by this ratio to get costs per NTC.
__ratio_of_NTC = 0.7
# Assume 75 % of overland distance as overhead lines, remaining 25 % are underground lines.
__ratio_of_overhead_over_land = 0.75

# Very rough estimate based on https://ec.europa.eu/research/participants/documents/downloadPublic?documentIds=080166e5bd374431&appId=PPGMS, Table 4 and on
# https://www.acer.europa.eu/sites/default/files/documents/Publications/ACER_UIC_indicators_table.pdf
# (no MVA rating provided, assuming quite pessimistic 1000 MVA per double-circuit line).
__interconnector_overhead_400kV_overnight_costs_per_mw_per_km_eur = 1500 / __ratio_of_NTC
__interconnector_underground_400kV_overnight_costs_per_mw_per_km_eur = 4000 / __ratio_of_NTC
# Rough estimates from https://www.researchgate.net/publication/350780302_Long-distance_renewable_hydrogen_transmission_via_cables_and_pipelines and
# https://www.researchgate.net/figure/HVDC-Submarine-cable-cost_tbl1_293959228
__interconnector_submarine_HVDC_overnight_costs_per_mw_per_km_eur = 3000 / __ratio_of_NTC

# O&M: very rough estimate as 2% of capex. Too small in total costs to get really precise numbers.
# Example of a very rough estimate for ČEPS: maintenance of old lines may be around 150m EUR per
# year (total investment per year is around 300m EUR, based on MAF 22) for 3500km at 400kV (and
# further 2000km at 220kV which we ignore for now). This is roughly 40k EUR per km per year. Even we
# assume the average rating of 2000 MVA, that would be roughly around 20 EUR per MW.
__interconnector_overhead_400kV_fixed_o_m_per_mw_per_km_eur = 20
__interconnector_submarine_HVDC_fixed_o_m_per_mw_per_km_eur = 40

# Rough estimate based on
# https://www.moorabool.vic.gov.au/files/assets/public/orphans/documents/20200924-msc-transmission-comparison-overhead-with-underground.pdf gives 2 years for a short segment
# of 75km. These are often much longer segments, increasing the time.
__interconnector_HVAC_construction_time_years = 5
# Rough estimate based on the following projects:
#  https://en.wikipedia.org/wiki/Viking_Link (4y)
#  https://en.wikipedia.org/wiki/NordBalt (2.5y)
#  https://en.wikipedia.org/wiki/NorNed (2.5y)
__interconnector_HVDC_construction_time_years = 3

# Charge a small fee per interconnector capacity, see https://www.enappsys.com/jaocapacity/.
OUTFLOW_CAPACITY_COST_EUR_PER_MWH = 2.0

_interconnectors = {
    "2021": {
        CZECHIA: {
            GERMANY: {"capacity_mw": __current_cz_de, "loss": __generic_transmission_loss},
            AUSTRIA: {"capacity_mw": __current_cz_at, "loss": __generic_transmission_loss},
            SLOVAKIA: {"capacity_mw": __current_cz_sk, "loss": __generic_transmission_loss},
            POLAND: {"capacity_mw": __current_cz_pl, "loss": __generic_transmission_loss},
        },
        GERMANY: {
            CZECHIA: {"capacity_mw": __current_de_cz, "loss": __generic_transmission_loss},
            POLAND: {"capacity_mw": __current_de_pl, "loss": __generic_transmission_loss},
            AUSTRIA: {"capacity_mw": __current_de_at_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
        },
        AUSTRIA: {
            SLOVAKIA: {"capacity_mw": __current_at_sk_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
            CZECHIA: {"capacity_mw": __current_at_cz, "loss": __generic_transmission_loss},
        },
        SLOVAKIA: {
            POLAND: {"capacity_mw": __current_sk_pl_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
            CZECHIA: {"capacity_mw": __current_sk_cz, "loss": __generic_transmission_loss},
        },
        POLAND: {
            GERMANY: {"capacity_mw": __current_pl_de, "loss": __generic_transmission_loss},
            CZECHIA: {"capacity_mw": __current_pl_cz, "loss": __generic_transmission_loss},
        }
    },
    # Based on the Stated Policy scenario in the EMBER dataset.
    "2030": {
        CZECHIA: {
            GERMANY: {"capacity_mw": __current_cz_de, "loss": __generic_transmission_loss},
            AUSTRIA: {"capacity_mw": __2030_stated_cz_at_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
            SLOVAKIA: {"capacity_mw": __current_cz_sk, "loss": __generic_transmission_loss},
            POLAND: {"capacity_mw": __current_cz_pl, "loss": __generic_transmission_loss},
        },
        GERMANY: {
            CZECHIA: {"capacity_mw": __current_de_cz, "loss": __generic_transmission_loss},
            POLAND: {"capacity_mw": __2030_stated_de_pl, "loss": __generic_transmission_loss},
            AUSTRIA: {"capacity_mw": __2030_stated_de_at_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
        },
        AUSTRIA: {
            SLOVAKIA: {"capacity_mw": __current_at_sk_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
        },
        SLOVAKIA: {
            POLAND: {"capacity_mw": __current_sk_pl_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
            CZECHIA: {"capacity_mw": __current_sk_cz, "loss": __generic_transmission_loss},
        },
        POLAND: {
            GERMANY: {"capacity_mw": __2030_stated_pl_de, "loss": __generic_transmission_loss},
            CZECHIA: {"capacity_mw": __current_pl_cz, "loss": __generic_transmission_loss},
        }
    },
    # Based on the System Change scenario in the EMBER dataset.
    "2030-ambitious": {
        CZECHIA: {
            GERMANY: {"capacity_mw": __current_cz_de, "loss": __generic_transmission_loss},
            AUSTRIA: {"capacity_mw": __2030_ambitious_cz_at_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
            SLOVAKIA: {"capacity_mw": __current_cz_sk, "loss": __generic_transmission_loss},
            POLAND: {"capacity_mw": __current_cz_pl, "loss": __generic_transmission_loss},
        },
        GERMANY: {
            CZECHIA: {"capacity_mw": __current_de_cz, "loss": __generic_transmission_loss},
            POLAND: {"capacity_mw": __2030_ambitious_de_pl, "loss": __generic_transmission_loss},
            AUSTRIA: {"capacity_mw": __2030_stated_de_at_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
        },
        AUSTRIA: {
            SLOVAKIA: {"capacity_mw": __2030_ambitious_at_sk, "loss": __generic_transmission_loss, "symmetric": True},
        },
        SLOVAKIA: {
            POLAND: {"capacity_mw": __current_sk_pl_symmetric, "loss": __generic_transmission_loss, "symmetric": True},
            CZECHIA: {"capacity_mw": __current_sk_cz, "loss": __generic_transmission_loss},
        },
        POLAND: {
            GERMANY: {"capacity_mw": __2030_ambitious_pl_de, "loss": __generic_transmission_loss},
            CZECHIA: {"capacity_mw": __current_pl_cz, "loss": __generic_transmission_loss},
        }
    },
}


class InterconnectorType(Enum):
    ''' Very simplistic classification of different types of interconnectors. '''
    MIXED_OVERHEAD_UNDERGROUND_AC = "land_ac"
    SUBMARINE_DC = "sea_dc"


@dataclass
class Interconnector:
    capacity_mw: float
    ''' Maximum power the interconnector can carry. '''
    paid_off_capacity_mw: float
    ''' Part of the capacity that should have no capex costs (i.e. preexisting capacity).'''
    loss: float
    ''' Loss as a ratio of the current flow. '''
    length_km: float
    ''' Length of the line in km. Costs of interconnectors are only calculated if this is non-zero'''
    type: InterconnectorType
    ''' Type of the link. '''


@dataclass
class Interconnectors:
    from_to: dict[Region, dict[Region, Interconnector]]

    def get_connections_from(self, source: Region) -> dict[Region, Interconnector]:
        return self.from_to.get(source, {})

    def get_connections_to(self, target: Region) -> dict[Region, Interconnector]:
        return {
            from_region: connection
            for from_region, to_dict in self.from_to.items()
            for to_region, connection in to_dict.items()
            if to_region == target
        }


InterconnectorsDict = dict[Region, dict[Region, dict]]


def _fix_interconnector_params(interconnector: dict) -> dict:
    interconnector.setdefault("capacity_mw", 0)
    interconnector.setdefault("paid_off_capacity_mw", 0)
    interconnector.setdefault("loss", 0)
    interconnector.setdefault("length_km", 0)
    interconnector.setdefault("type", InterconnectorType.MIXED_OVERHEAD_UNDERGROUND_AC)
    return interconnector


def _build_interconnectors(interconnectors: InterconnectorsDict,
                           countries: Collection[Region]) -> Interconnectors:
    map_from_to: dict[Region, dict[Region, Interconnector]] = {
        country: {} for country in countries}
    for country_from, to_dict in interconnectors.items():
        for country_to, params in to_dict.items():
            if country_from in countries and country_to in countries:
                symmetric = params.pop("symmetric", False)
                fixed = _fix_interconnector_params(params)
                map_from_to[country_from][country_to] = Interconnector(**fixed)
                if symmetric:
                    map_from_to[country_to][country_from] = Interconnector(**fixed)
    return Interconnectors(from_to=map_from_to)


def get_interconnectors(interconnectors, countries: set[Region]) -> Interconnectors:
    if isinstance(interconnectors, str):
        source_dict = deepcopy(_interconnectors[interconnectors])
    else:
        source_dict = deepcopy(interconnectors)
    return _build_interconnectors(source_dict, countries)


def aggregate_interconnectors(interconnectors: InterconnectorsDict, aggregate_countries: Collection[AggregateRegion]) -> InterconnectorsDict:
    def get_type(types: set[InterconnectorType]) -> InterconnectorType:
        if len(types) == 2:
            # In case of both types of connection, stick to the overhead type.
            return InterconnectorType.MIXED_OVERHEAD_UNDERGROUND_AC
        elif len(types) == 1:
            return types.pop()
        else:
            assert len(types) == 0, f"unexpected interconnector types encountered {types}"
            # Return a default value.
            return InterconnectorType.MIXED_OVERHEAD_UNDERGROUND_AC

    for aggregate in aggregate_countries:
        parts = get_aggregated_countries(aggregate)
        for country_from in interconnectors:
            def get_range_from(key: str):
                return [interconnectors[country_from][country_to][key] for country_to in parts
                        if country_to in interconnectors[country_from]]
            if country_from in parts:
                continue
            import_capacity = sum(get_range_from("capacity_mw"))
            if import_capacity == 0:
                continue
            type = get_type(set(get_range_from("type")))
            interconnectors[country_from][aggregate] = {
                "capacity_mw": import_capacity,
                "paid_off_capacity_mw": sum(get_range_from("paid_off_capacity_mw")),
                # This is an under-approximation for very coarse aggregates (as it ignores losses
                # _within_ the aggregate).
                "loss": mean(get_range_from("loss")),
                "type": type,
            }
            for country_to in parts:
                if country_to in interconnectors[country_from]:
                    del interconnectors[country_from][country_to]
        interconnectors[aggregate] = {}
        for country_to in interconnectors:
            def get_range_to(key: str):
                return [interconnectors[country_from][country_to][key] for country_from in parts
                        if country_to in interconnectors[country_from]]
            if country_to in parts:
                continue
            export_capacity = sum(get_range_to("capacity_mw"))
            if export_capacity == 0:
                continue
            type = get_type(set(get_range_to("type")))
            interconnectors[aggregate][country_to] = {
                "capacity_mw": export_capacity,
                "paid_off_capacity_mw": sum(get_range_to("paid_off_capacity_mw")),
                # This is an under-approximation for very coarse aggregates (as it ignores losses
                # _within_ the aggregate).
                "loss": mean(get_range_to("loss")),
                "type": type,
            }
        for country_from in parts:
            del interconnectors[country_from]
    return interconnectors


def get_loss_per_distance(distance_km: float, type: InterconnectorType) -> float:
    distance_in_tkm = distance_km / 1000
    if type == InterconnectorType.MIXED_OVERHEAD_UNDERGROUND_AC:
        return __AC_transmission_loss_base + __AC_transmission_loss_per_1000_km * distance_in_tkm
    elif type == InterconnectorType.SUBMARINE_DC:
        return __HVDC_transmission_loss_base + __HVDC_transmission_loss_per_1000_km * distance_in_tkm
    assert False, "Unknown type provided"


def add_distances_type_and_loss_to_interconnectors(interconnectors: InterconnectorsDict) -> None:
    # Add lengths of interconnectors (based on capital distances) and give better estimates of
    # transmission loss based on those distances.
    for country_from, dict_to in interconnectors.items():
        for country_to, interconnector in dict_to.items():
            distance = get_transmission_distance_km(country_from, country_to)
            assert distance, f"missing distance between {country_from} and {country_to}"
            (distance_km, overland) = distance
            type: InterconnectorType = \
                InterconnectorType.MIXED_OVERHEAD_UNDERGROUND_AC if overland else InterconnectorType.SUBMARINE_DC
            interconnector["type"] = type
            interconnector["length_km"] = distance_km
            interconnector["loss"] = get_loss_per_distance(distance_km, type)


def get_expansion_capex_per_year_eur(capacity_mw: float,
                                     distance_km: float,
                                     type: InterconnectorType) -> float:
    if type == InterconnectorType.MIXED_OVERHEAD_UNDERGROUND_AC:
        fixed_o_m_costs_per_mw_per_km_eur = __interconnector_overhead_400kV_fixed_o_m_per_mw_per_km_eur
        overhead = __ratio_of_overhead_over_land
        underground = 1 - overhead
        overnight_costs_per_mw_per_km_eur = \
            overhead * __interconnector_overhead_400kV_overnight_costs_per_mw_per_km_eur + \
            underground * __interconnector_underground_400kV_overnight_costs_per_mw_per_km_eur
        construction_time_years = __interconnector_HVAC_construction_time_years
        lifetime_years = __interconnector_HVAC_lifetime_years
    elif type == InterconnectorType.SUBMARINE_DC:
        fixed_o_m_costs_per_mw_per_km_eur = __interconnector_submarine_HVDC_fixed_o_m_per_mw_per_km_eur
        overnight_costs_per_mw_per_km_eur = __interconnector_submarine_HVDC_overnight_costs_per_mw_per_km_eur
        construction_time_years = __interconnector_HVDC_construction_time_years
        lifetime_years = __interconnector_HVDC_lifetime_years
    else:
        assert False, "Unknown type provided"

    return get_interconnector_capex_per_year_eur(capacity_mw, distance_km,
                                                 fixed_o_m_costs_per_mw_per_km_eur,
                                                 overnight_costs_per_mw_per_km_eur,
                                                 construction_time_years,
                                                 lifetime_years,
                                                 __interconnector_discount_rate)


def load_interconnectors_from_ember_ng(df: pandas.DataFrame,
                                       scenario: str,
                                       year: int,
                                       base_year: int,
                                       countries: Optional[Collection[Zone]] = None) \
        -> InterconnectorsDict:
    """
    Load interconnector capacities from Ember New Generation [1] raw
    data file.

    Arguments:
        df: Pandas data frame of the Ember New Generation
            interconnectors dataset.
        scenario: Name of scenario to load.
        year: Target year for interconnector capacities. Available years
            range between 2020 and 2050 in 5-year increments.
        base_year: Base year for interconnector capacities (used for
            assessing amount of expansion). Available years range between
            2020 and 2050 in 5-year increments.
        countries: Collection (set or list) of codes of countries whose
            interconnector capacities should be loaded. If empty, all
            available countries are loaded.

    Returns:
        Collection of nested dictionaries with parameters of the
        requested interconnector capacities from Ember NG.

    [1]: https://ember-climate.org/insights/research/new-generation/
    """
    # Validate arguments.
    if scenario not in df["Scenario"].unique():
        raise ValueError(f"Invalid Ember New Generation scenario ‘{scenario}’")
    if year not in df["Trajectory year"].unique():
        raise ValueError(f"Invalid Ember New Generation target year ‘{year}’")

    base_df = df[(df["KPI"] == "Transmission capacities") &
                 (df["Scenario"] == scenario) &
                 (df["Trajectory year"] == base_year)]
    target_df = df[(df["KPI"] == "Transmission capacities") &
                   (df["Scenario"] == scenario) &
                   (df["Trajectory year"] == year)]

    map_from_to: dict[Region, dict[Region, dict]] = {}
    for country_from, intercons_df in target_df.groupby("Export Country"):
        country_from = Region(country_from)
        if countries and country_from not in countries:
            continue
        map_from_to[country_from] = {}
        for intercon_row in intercons_df.itertuples():
            country_to = Region(intercon_row[6])
            if countries and country_to not in countries:
                continue
            map_from_to[country_from][country_to] = {
                "capacity_mw": intercon_row.Result * 1000,
                "loss": __generic_transmission_loss,
            }

    # Add paid off capacities from the base dataframe.
    for country_from, intercons_df in base_df.groupby("Export Country"):
        country_from = Region(country_from)
        if country_from not in map_from_to:
            continue
        for intercon_row in intercons_df.itertuples():
            country_to = Region(intercon_row[6])
            if country_to not in map_from_to[country_from]:
                continue
            map_from_to[country_from][country_to]["paid_off_capacity_mw"] = intercon_row.Result * 1000

    return map_from_to

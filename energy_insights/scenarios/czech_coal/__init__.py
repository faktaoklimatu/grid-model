import os
from copy import deepcopy
from functools import cache
from typing import Optional

from ...loaders import Pemmdb2025Loader
from ...logging import get_logger
from ...params_library.installed import get_installed_gw
from ...params_library.interconnectors import InterconnectorsDict
from ...region import *
from ...sources.basic_source import BasicSourceType
from ...sources.flexible_source import FlexibleSourceType, flexible_source_defaults
from ...sources.input_costs import get_input_costs
from ...sources.storage import StorageType

# NOTE: This is exported.
from .scenarios import ScenarioSpec, cz_coal_scenarios

logger = get_logger(__name__)

# Assumed lignite prices after 2025 for coal scenarios modelling.
# Prices in 2024 €/MWh.
# Source: ERAA 2025 post-CfE preliminary data, dataset 'Commodity Prices.csv'
_lignite_price_groups = [
    {
        "countries": "BG CZ MK".split(),
        "lignite_price_per_mwh_LHV_eur": 6.69,
    },
    {
        "countries": "BA DE GB IE ME PL RS SK".split(),
        "lignite_price_per_mwh_LHV_eur": 8.6,
    },
    {
        "countries": "HU RO SI".split(),
        "lignite_price_per_mwh_LHV_eur": 11.33,
    },
    {
        "countries": "GR TR".split(),
        "lignite_price_per_mwh_LHV_eur": 14.82,
    },
]

_default_input_costs = "2028"

# Derating factors to accont for the difference in net output compared
# to nominal capacity. Approximated according to figures in ERÚ reports
# (self-consumption for electricity and heat production).
_coal_net_capacity_derating = 0.12
_ccgt_net_capacity_derating = 0.02
# Applies to OCGT, biogas peaker and waste.
_ocgt_net_capacity_derating = 0.07
# Applies to biomass as well as biogas and biomethane.
_biomass_net_capacity_derating = _ocgt_net_capacity_derating
_engines_net_capacity_derating = _ocgt_net_capacity_derating


_BIOMASS_TYPES = {
    FlexibleSourceType.BIOGAS,
    FlexibleSourceType.SOLID_BIOMASS,
    FlexibleSourceType.SOLID_BIOMASS_CHP,
}

_CCGT_TYPES = {
    FlexibleSourceType.GAS_CCGT,
    FlexibleSourceType.GAS_CCGT_CCS,
    FlexibleSourceType.GAS_CHP,
}

_COAL_TYPES = {
    FlexibleSourceType.COAL,
    FlexibleSourceType.COAL_BACKPRESSURE,
    FlexibleSourceType.COAL_EXTRACTION,
    FlexibleSourceType.COAL_SUPERCRITICAL,
    FlexibleSourceType.LIGNITE,
    FlexibleSourceType.LIGNITE_BACKPRESSURE,
    FlexibleSourceType.LIGNITE_EXTRACTION,
    FlexibleSourceType.LIGNITE_OLD,
    FlexibleSourceType.LIGNITE_SUPERCRITICAL,
}

_ENGINE_TYPES = {FlexibleSourceType.GAS_ENGINE, FlexibleSourceType.GAS_ENGINE_CHP}

_OCGT_TYPES = {
    FlexibleSourceType.BIOGAS_PEAK,
    FlexibleSourceType.GAS_PEAK,
    FlexibleSourceType.WASTE,
}


def _construct_grid(
    pemmdb_loader: Pemmdb2025Loader,
    pemmdb_year: int,
    aggregation_level: Optional[str] = None,
    include_reserves=False,
    post_eva=False,
):
    if aggregation_level == "cz":
        return {
            "countries": {},
        }

    if aggregation_level == "ce":
        return {
            "countries": {
                AUSTRIA: pemmdb_loader.get_country(
                    AUSTRIA,
                    pemmdb_year,
                    include_reserves=include_reserves,
                    post_eva=post_eva,
                ),
                GERMANY: pemmdb_loader.get_country(
                    GERMANY,
                    pemmdb_year,
                    include_reserves=include_reserves,
                    post_eva=post_eva,
                ),
                POLAND: pemmdb_loader.get_country(
                    POLAND,
                    pemmdb_year,
                    include_reserves=include_reserves,
                    post_eva=post_eva,
                ),
                SLOVAKIA: pemmdb_loader.get_country(
                    SLOVAKIA,
                    pemmdb_year,
                    include_reserves=include_reserves,
                    post_eva=post_eva,
                ),
            },
            "interconnectors": pemmdb_loader.get_interconnectors(
                year=pemmdb_year,
                countries=[AUSTRIA, CZECHIA, GERMANY, POLAND, SLOVAKIA],
            ),
        }

    all_countries = ALL_COUNTRIES - {CYPRUS, MALTA}

    if aggregation_level is None:
        aggregates: set[AggregateRegion] = set()
        aggregated_countries: set[Zone] = set()
    elif aggregation_level not in REGION_AGGREGATION_LEVELS:
        raise KeyError(f"Uknown country aggregation level '{aggregation_level}'")
    else:
        # List countries that are part of any aggregate.
        aggregates = REGION_AGGREGATION_LEVELS[aggregation_level]
        aggregated_countries = set.union(
            *(get_aggregated_countries(agg) for agg in aggregates)
        )

    # Set of countries that are not part of any aggregate.
    standalone_countries = all_countries - aggregated_countries - {CZECHIA}

    countries_dict: dict[Zone, dict] = {
        country: pemmdb_loader.get_country(
            country,
            pemmdb_year,
            include_reserves=include_reserves,
            post_eva=post_eva,
        )
        for country in standalone_countries
    }

    for aggregate in aggregates:
        aggregate_dict = pemmdb_loader.get_countries_from_aggregate(
            aggregate,
            pemmdb_year,
            include_reserves=include_reserves,
            post_eva=post_eva,
        )
        countries_dict |= aggregate_dict

    return {
        "countries": countries_dict,
        "interconnectors": pemmdb_loader.get_interconnectors(
            year=pemmdb_year,
            countries=all_countries,
            aggregate_countries=aggregates,
        ),
    }


def _get_lignite_price(country: Zone) -> Optional[float]:
    for price_group in _lignite_price_groups:
        if country in price_group["countries"]:
            return price_group["lignite_price_per_mwh_LHV_eur"]

    return None


def _make_adjustments(region_spec: dict, adjustments: Optional[dict] = None) -> None:
    if not adjustments:
        return

    for source_type, new_params in adjustments.items():
        if source_type in BasicSourceType:
            # Ignore economics-only adjustment unless the source is
            # already specified in the country.
            if (
                source_type not in region_spec["basic_sources"]
                and "capacity_mw" not in new_params
            ):
                continue

            params = region_spec["basic_sources"].setdefault(source_type, {})
            params |= new_params

            # Overwrite minimum capacity if max is specified but min isn't.
            if "capacity_mw" in new_params and "min_capacity_mw" not in new_params:
                params["min_capacity_mw"] = new_params["capacity_mw"]
        elif source_type in FlexibleSourceType:
            # Ignore economics-only adjustment unless the source is
            # already specified in the country.
            if (
                source_type not in region_spec["flexible_sources"]
                and "capacity_mw" not in new_params
            ):
                continue

            params = region_spec["flexible_sources"].setdefault(source_type, {})
            params |= new_params

            # Overwrite minimum capacity if max is specified but min isn't.
            if "capacity_mw" in new_params and "min_capacity_mw" not in new_params:
                params["min_capacity_mw"] = new_params["capacity_mw"]
        elif source_type in StorageType:
            # Ignore economics-only adjustment unless the source is
            # already specified in the country.
            if (
                source_type not in region_spec["storage"]
                and "capacity_mw" not in new_params
                and "capacity_mw_charging" not in new_params
            ):
                continue

            storage = region_spec["storage"].setdefault(source_type, {})
            storage |= new_params

            # Overwrite minimum capacity if max is specified but min isn't.
            if "capacity_mw" in new_params and "min_capacity_mw" not in new_params:
                storage["min_capacity_mw"] = new_params["capacity_mw"]
            if (
                "capacity_mw_charging" in new_params
                and "min_capacity_mw_charging" not in new_params
            ):
                storage["min_capacity_mw_charging"] = new_params["capacity_mw_charging"]
        elif source_type != "interconnectors":
            raise KeyError(f"Unknown source type '{source_type}'")


@cache
def get_pemmdb_loader(root_dir: str = ".") -> Pemmdb2025Loader:
    data_directory = os.path.join(root_dir, "data", "pemmdb")
    return Pemmdb2025Loader(data_directory=data_directory)


def make_scenario(
    name: str,
    scenario_spec: ScenarioSpec,
    *,
    pemmdb_loader: Pemmdb2025Loader,
    entsoe_year: int,
    aggregation_level: Optional[str] = None,
    optimize_heat=False,
    include_reserves=False,
    lignite_price_groups=False,
) -> dict:
    pemmdb_year: int = scenario_spec["target_year"]
    cz_adjustments = scenario_spec.get("adjustments")
    global_adjustments = scenario_spec.get("global_adjustments")
    global_input_costs = scenario_spec.get("input_costs", _default_input_costs)
    post_eva = scenario_spec.get("post_eva", False)

    czechia = pemmdb_loader.get_country(
        CZECHIA, pemmdb_year, include_reserves=include_reserves
    )

    # Apply net capacity derating to Czech sources (they are specified
    # as gross capacities in the input datasheet).
    for key, params in cz_adjustments.items():
        if "capacity_mw" not in params:
            continue

        if key in _BIOMASS_TYPES:
            params["capacity_mw"] *= 1.0 - _biomass_net_capacity_derating
        elif key in _CCGT_TYPES:
            params["capacity_mw"] *= 1.0 - _ccgt_net_capacity_derating
        elif key in _COAL_TYPES:
            params["capacity_mw"] *= 1.0 - _coal_net_capacity_derating
        elif key in _ENGINE_TYPES:
            params["capacity_mw"] *= 1.0 - _engines_net_capacity_derating
        elif key in _OCGT_TYPES:
            params["capacity_mw"] *= 1.0 - _ocgt_net_capacity_derating

    if optimize_heat:
        czechia["heat_demand"] = True
        # NOTE: Historic temperatures are only used to estimate the sensitivity
        # of heat demand to air temperatures, i.e. the temperature–heat demand
        # curve.
        czechia["historic_temperatures"] = "ERA5-CZ.csv"

    if cz_load_factors := scenario_spec.get("load_factors"):
        czechia["load_factors"] |= cz_load_factors

    context_grid = _construct_grid(
        pemmdb_loader,
        pemmdb_year,
        aggregation_level=aggregation_level,
        include_reserves=include_reserves,
        post_eva=post_eva,
    )

    # Make sure Czechia is plotted first for faster debugging.
    context_grid["countries"] = {CZECHIA: czechia} | context_grid["countries"]

    # Adjust lignite prices to match ENTSO-E ERAA assumptions.
    if lignite_price_groups:
        # Lignite price stratification is only supported for
        # no aggregation and fine aggregation level.
        if aggregation_level is not None and aggregation_level != "fine":
            logger.warning(
                "Stratified lignite prices requested, but aggregation level must be ‘none’ or ‘fine’"
            )
        else:
            for country_code, country_spec in context_grid["countries"].items():
                if lignite_price := _get_lignite_price(country_code):
                    country_spec["input_costs"] = get_input_costs(
                        country_spec.get("input_costs", global_input_costs)
                    )
                    country_spec["input_costs"].lignite_price_per_mwh_LHV_eur = (
                        lignite_price
                    )

    if germany := context_grid["countries"].get(GERMANY):
        # According to the Global Coal Plant Tracker, around 2025,
        # about 8.26 GW of the lignite-fired and 6.74 GW of the hard/
        # /bituminous coal-fired plants in Germany have supercritical
        # combustion. This is around 56% and 52% of the total, resp.
        # We assume the ratio will favour supercriticals even more
        # going forward, as old coal plants shut down.
        coal_de = germany["flexible_sources"][FlexibleSourceType.COAL]
        lig_de = germany["flexible_sources"][FlexibleSourceType.LIGNITE]

        coal_sc_de = {"capacity_mw": coal_de["capacity_mw"] * 0.64}
        lig_sc_de = {"capacity_mw": lig_de["capacity_mw"] * 0.59}

        germany["flexible_sources"][FlexibleSourceType.COAL_SUPERCRITICAL] = coal_sc_de
        germany["flexible_sources"][
            FlexibleSourceType.LIGNITE_SUPERCRITICAL
        ] = lig_sc_de

        coal_de["capacity_mw"] -= coal_sc_de["capacity_mw"]
        lig_de["capacity_mw"] -= lig_sc_de["capacity_mw"]

    if great_britain := context_grid["countries"].get(GREAT_BRITAIN):
        # The figure for nuclear installed capacity in PEMMDB is
        # clearly incorrect. It is 5.88 GW as of 2024 according to Ember.
        great_britain["basic_sources"][BasicSourceType.NUCLEAR]["capacity_mw"] = 5880

    if netherlands := context_grid["countries"].get(NETHERLANDS):
        # All of the Netherlands' coal-fired plants are supercritical.
        netherlands["flexible_sources"][FlexibleSourceType.COAL_SUPERCRITICAL] = (
            deepcopy(netherlands["flexible_sources"][FlexibleSourceType.COAL])
        )
        del netherlands["flexible_sources"][FlexibleSourceType.COAL]

    if poland := context_grid["countries"].get(POLAND):
        # According to the Global Coal Plant Tracker, around 2025,
        # Poland has about 2.9 GW of supercritical lignite-fired and
        # 3.2 GW of supercritical hard coal-fired plants. This
        # corresponds to about 45% and 22%, respectively.
        # We assume the ratio will favour supercriticals even more
        # going forward, as old coal plants shut down.
        coal_pl = poland["flexible_sources"][FlexibleSourceType.COAL]
        lig_pl = poland["flexible_sources"][FlexibleSourceType.LIGNITE]

        coal_sc_pl = {"capacity_mw": coal_pl["capacity_mw"] * 0.25}
        lig_sc_pl = {"capacity_mw": lig_pl["capacity_mw"] * 0.46}

        poland["flexible_sources"][FlexibleSourceType.COAL_SUPERCRITICAL] = coal_sc_pl
        poland["flexible_sources"][FlexibleSourceType.LIGNITE_SUPERCRITICAL] = lig_sc_pl

        coal_pl["capacity_mw"] -= coal_sc_pl["capacity_mw"]
        lig_pl["capacity_mw"] -= lig_sc_pl["capacity_mw"]

    # Apply source adjustments to all regions if requested.
    for country, country_spec in context_grid["countries"].items():
        # Special handling of nuclear because it's the only time
        # series for which we still use historical ENTSO-E data.
        # We need to scale the production from the historical installed
        # capacity to the present/future capacity (which is usually
        # lower).
        if nuclear := country_spec["basic_sources"].get(BasicSourceType.NUCLEAR):
            if nuclear["capacity_mw"] > 0:
                installed_gw_map = get_installed_gw(country, entsoe_year) or {}
                historical_capacity_gw = installed_gw_map.get(BasicSourceType.NUCLEAR)
                pemmdb_capacity_gw = country_spec["installed_gw"][
                    BasicSourceType.NUCLEAR
                ]

                if historical_capacity_gw is None and pemmdb_capacity_gw > 0:
                    logger.warning(
                        f"Missing historical nuclear installed capacity in {country} {entsoe_year}"
                        f"; using PEMMDB capacity ({pemmdb_capacity_gw:.3f} GW) for scaling"
                    )
                    continue

                if (
                    historical_capacity_gw
                    and historical_capacity_gw != pemmdb_capacity_gw
                ):
                    logger.warning(
                        f"Adjusting historical nuclear capacity in {country}: "
                        f"{pemmdb_capacity_gw:.3f} → {historical_capacity_gw:.3f} GW"
                    )
                    country_spec["installed_gw"][
                        BasicSourceType.NUCLEAR
                    ] = historical_capacity_gw

        if global_adjustments:
            _make_adjustments(country_spec, global_adjustments)

    if "interconnectors" in scenario_spec and "interconnectors" in context_grid:
        new_capacities: dict[str, float] = scenario_spec["interconnectors"]
        interconnectors = context_grid["interconnectors"]
        for key, capacity_mw in new_capacities.items():
            if "->" in key:
                from_region, to_region = key.split("->")
                if (
                    from_region not in interconnectors
                    or to_region not in interconnectors[from_region]
                ):
                    continue
                interconnectors[from_region][to_region]["capacity_mw"] = capacity_mw
            else:
                raise ValueError(f"Invalid interconnector specifier '{key}'")

    # Czechia's country-specific adjustments take precedence over
    # universal global adjustments.
    _make_adjustments(
        czechia,
        {
            # Take global adjustments (e.g. for costs or capacity
            # factor constraints) from global adjustments for sources
            # that might be new in Czechia.
            key: global_adjustments.get(key, {}) | value
            for key, value in cz_adjustments.items()
        },
    )

    if flexible_derating := scenario_spec.get("flexible_derating"):
        assert 0.0 <= flexible_derating < 1.0
        logger.debug(f"Derating all flexible sources by {100 * flexible_derating}%")

        for country_spec in context_grid["countries"].values():
            for source_type, flexible_source in country_spec[
                "flexible_sources"
            ].items():
                flexible_source["capacity_mw"] *= 1.0 - flexible_derating
                if "min_capacity_mw" in flexible_source:
                    flexible_source["min_capacity_mw"] *= 1.0 - flexible_derating
                uptime_ratio = flexible_source.get(
                    "uptime_ratio",
                    flexible_source_defaults[source_type].get("uptime_ratio", 1.0),
                )
                flexible_source["uptime_ratio"] = min(
                    1.0, uptime_ratio / (1.0 - flexible_derating)
                )

    scenario_out = context_grid | {
        "name": name,
        "input_costs": global_input_costs,
        "pecd_target_year": pemmdb_year,
    }

    return scenario_out


def minimize_sources(sources1: dict, sources2: dict, buildout_factor: float) -> None:
    for source, source_spec in sources1.items():
        capacity1 = source_spec["capacity_mw"]
        capacity2 = sources2.get(source, {}).get("capacity_mw", 0)
        capacity_mw = capacity2
        # Reduce if new capacity should get build out.
        if capacity2 > capacity1:
            capacity_mw = capacity1 + (capacity2 - capacity1) * buildout_factor

        source_spec["capacity_mw"] = capacity_mw
        source_spec["min_capacity_mw"] = capacity_mw


def scale_intercon_capacities(scenario: dict, factor: float) -> dict:
    interconnectors: InterconnectorsDict = scenario["interconnectors"]

    for destination_map in interconnectors.values():
        for link_spec in destination_map.values():
            link_spec["capacity_mw"] *= factor

    return scenario


def make_pessimistic_scenario(
    name: str,
    base_scenario: dict,
    future_scenario: dict,
    buildout_factor: float = 1.0,
    demand_scale: float = 1.0,
) -> dict:
    # We start from the future in order to capture future demand.
    scenario_min = deepcopy(future_scenario)
    scenario_min["name"] = name
    # Reduce interconnection capacities uniformly by 20% compared
    # to the base scenario (2025).
    if "interconnectors" in scenario_min:
        scenario_min["interconnectors"] = deepcopy(base_scenario["interconnectors"])
        scale_intercon_capacities(scenario_min, 0.8)

    for country, spec_min in scenario_min["countries"].items():
        spec_base = base_scenario["countries"][country]

        # Reconcile basic sources.
        minimize_sources(
            spec_base["basic_sources"], spec_min["basic_sources"], buildout_factor
        )

        # Reconcile flexible sources.
        minimize_sources(
            spec_base["flexible_sources"], spec_min["flexible_sources"], buildout_factor
        )

        # Keep storage at 2025 levels. We assume it's not going to
        # decrease anywhere.

    # Reduce interconnection capacities uniformly by 20%.
    if "interconnectors" in scenario_min:
        scale_intercon_capacities(scenario_min, 0.8)

    # Increase Czech electricity demand uniformly by a given factor
    # (compared to the base scenarios, which was decreased to 90% of
    # the original PECD demand).
    # scenario_min["countries"][CZECHIA]["load_factors"]["load_base"] = 0.9 * demand_scale

    return scenario_min

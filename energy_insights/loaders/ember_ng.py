from collections.abc import Collection
from functools import cached_property, cache
from pathlib import Path
from typing import Any, Optional, Union

import pandas

from .entsoe import EntsoeLoader
from .pecd import PecdLoader
from ..grid_plot_utils import get_basic_key, Keys
from ..params_library.basic_source import load_basic_sources_from_ember_ng
from ..params_library.flexible_source import load_flexible_sources_from_ember_ng
from ..params_library.installed import load_installed_and_production_from_ember_ng
from ..params_library.interconnectors import (
    InterconnectorsDict,
    add_distances_type_and_loss_to_interconnectors,
    aggregate_interconnectors,
    load_interconnectors_from_ember_ng,
)
from ..params_library.load_factors import LoadFactors, load_load_factors_from_ember_ng
from ..params_library.storage import load_hydro_storage_from_pecd, load_storage_from_ember_ng
from ..region import *
from ..sources.basic_source import BasicSourceType, ProfileOverride
from ..sources.flexible_source import FlexibleSourceType


class EmberNgLoader:
    """
    Load parameter values (source and interconnector capacities, demand
    factors, etc.) from the Ember New Generation [1] dataset.

    [1]: https://ember-climate.org/insights/research/new-generation/
    """

    # Core pathways.
    STATED_POLICY = "Stated Policy"
    SYSTEM_CHANGE = "System Change"
    TECHNOLOGY_DRIVEN = "Technology Driven"

    # Additional pathways.
    ALTERNATIVE_HYDROGEN_SUPPLY = "Alternative Hydrogen Supply"
    DELAYED_INTERCONNECTIONS = "Delayed Interconnections"
    HIGHER_FOSSIL_FUEL_PRICES = "Higher Fossil Fuel Prices"
    LIMITED_NEW_GAS = "Limited New Gas"
    LOWER_DEMAND_FLEXIBILITY = "Lower Demand Flexibility"
    NO_GAS_WITH_CCS = "No Gas+CCS"
    NUCLEAR_PLUS = "Nuclear Plus"
    RESISTANCE_TO_RES = "Resistance to RES"
    SYSTEM_CHANGE_BATTERY = "System Change - Battery"
    TECHNOLOGY_DRIVEN_BATTERY = "Technology Driven - Battery"

    TYNDP_BASE_SCENARIO = "REF 2019"
    TYNDP_TARGET_SCENARIO = "DE 2050"

    # Deal with differences in country codes vs. Ember dataset.
    _COUNTRY_MAP: dict[Zone, Region] = {
        GREAT_BRITAIN: Region("UK")
    }

    def __init__(self,
                 entsoe_years: list[int],
                 pecd_years: list[int],
                 pecd_normalization_years: Optional[list[int]],
                 common_years: list[int],
                 data_file: Union[str, Path],
                 tyndp_input_file: Union[str, Path],
                 load_hydro_from_pecd: bool,
                 load_demand_from_pecd: bool,
                 entsoe_loader: Optional[EntsoeLoader] = None,
                 pecd_loader: Optional[PecdLoader] = None) -> None:
        assert not pecd_normalization_years or set(pecd_years).issubset(set(pecd_normalization_years)), \
            f"PECD year {pecd_years} not in PECD normalization years: {pecd_normalization_years}"
        assert len(entsoe_years) == len(pecd_years) and len(pecd_years) == len(common_years)
        assert len(entsoe_years) >= 1, "at least one year must be provided"
        self._entsoe_years = entsoe_years
        self._pecd_years = pecd_years
        self._pecd_normalization_years = pecd_normalization_years
        self._common_years = common_years
        self._data_file = data_file
        self._tyndp_input_file = tyndp_input_file
        self._base_year = 2020
        self._load_hydro_from_pecd = load_hydro_from_pecd
        self._load_demand_from_pecd = load_demand_from_pecd
        self._entsoe_loader = entsoe_loader
        self._pecd_loader = pecd_loader

    @cached_property
    def _df_intercon(self):
        return pandas.read_excel(self._data_file,
                                 sheet_name="Raw Data - Interconnection",
                                 engine="openpyxl")

    @cached_property
    def _df_sources(self):
        return pandas.read_excel(self._data_file, sheet_name="Raw Data", engine="openpyxl")

    @cached_property
    def _df_demand(self):
        return pandas.read_excel(self._tyndp_input_file, sheet_name="3_DEMAND_OUTPUT", engine="pyxlsb")

    def _map_to_ember_region(self, country: Zone) -> Region:
        return EmberNgLoader._COUNTRY_MAP.get(country, country)

    def get_basic_sources(self,
                          scenario: str,
                          target_year: int,
                          country: Zone,
                          allow_capex_optimization: bool = False,
                          profile_overrides: Optional[dict[BasicSourceType, Zone]] = None) \
            -> dict[BasicSourceType, dict]:
        sources = load_basic_sources_from_ember_ng(self._df_sources,
                                                   scenario=scenario,
                                                   year=target_year,
                                                   country=self._map_to_ember_region(country),
                                                   allow_capex_optimization_against_base_year=self._base_year if allow_capex_optimization else None,
                                                   load_hydro=not self._load_hydro_from_pecd)
        if profile_overrides:
            for source, override_country in profile_overrides.items():
                if source in sources:
                    override_installed = self.get_installed(
                        scenario, target_year, override_country)[source]
                    sources[source]["profile_override"] = ProfileOverride(
                        override_country, override_installed, source)
        return sources

    def get_pecd_normalization_factors(self,
                                       scenario: str,
                                       target_year: int,
                                       country: Zone) -> dict[BasicSourceType, float]:
        assert self._extrapolator, "get_pecd_normalization_factors() needs an extrapolator"
        assert self._pecd_loader, "PECD loader is needed to calculate normalization factors"

        if self._pecd_normalization_years:
            normalization_years = self._pecd_normalization_years
            # Fake a list of common years, is not that important.
            common_years = [self._common_years[0] for y in normalization_years]
        elif self._pecd_years:
            normalization_years = self._pecd_years
            common_years = self._common_years
        else:
            return {}

        installed_gw_and_production_twh_map = \
            load_installed_and_production_from_ember_ng(self._df_sources,
                                                        scenario=scenario,
                                                        year=target_year,
                                                        country=self._map_to_ember_region(country))
        pecd_data_maps: dict[int, dict[BasicSourceType, Optional[pandas.Series]]] = {}
        for (normalization_year, common_year) in zip(normalization_years, common_years):
            pecd_data_maps[normalization_year] = \
                self._pecd_loader.load_basic_sources_map(country, normalization_year,
                                                         self._common_year)

        normalization_factors: dict[BasicSourceType, float] = {}
        for source, (installed_gw, production_twh) in installed_gw_and_production_twh_map.items():
            # Skip sources with less than 100 kW of installed capacity.
            if installed_gw < 1e-4:
                continue

            pecd_production_twh = 0
            for normalization_year in normalization_years:
                data_map = pecd_data_maps[normalization_year]
                if data_map.get(source) is None:
                    continue
                pecd_production_twh += data_map[source].sum() * installed_gw / 1_000
            average_pecd_production_twh = pecd_production_twh / len(normalization_years)
            if average_pecd_production_twh > 0:
                normalization_factors[source] = production_twh / average_pecd_production_twh

        return normalization_factors

    def get_installed(self,
                      scenario: str,
                      target_year: int,
                      country: Zone) -> dict[BasicSourceType, float]:
        assert self._entsoe_loader, "get_installed() needs an ENTSOE-E loader"

        installed_gw_and_production_twh_map = \
            load_installed_and_production_from_ember_ng(self._df_sources,
                                                        scenario=scenario,
                                                        year=target_year,
                                                        country=self._map_to_ember_region(country))
        base_installed_gw_and_production_twh_map = \
            load_installed_and_production_from_ember_ng(self._df_sources,
                                                        scenario=scenario,
                                                        year=self._base_year,
                                                        country=self._map_to_ember_region(country))
        base_data_sums = pandas.Series()
        for (entsoe_year, common_year) in zip(self._entsoe_years, self._common_years):
            base_data: pandas.DataFrame = self._entsoe_loader.load_country_year_data(
                country, entsoe_year, common_year)
            if base_data_sums.empty:
                base_data_sums = base_data.sum()
            else:
                base_data_sums += base_data.sum()
        base_data_sums /= len(self._entsoe_years)

        base_installed_gw_map: dict[BasicSourceType, float] = {}
        for source, (installed_gw, production_twh) in installed_gw_and_production_twh_map.items():
            if production_twh <= 0:
                # If the target production (and thus also target `installed_gw`) is zero, provide a
                # meaningful number using `base_installed_gw`, instead.
                base_installed_gw, _ = base_installed_gw_and_production_twh_map[source]
                base_installed_gw_map[source] = base_installed_gw
            else:
                # Rescale the target installation down linearly based on production (if `base_data_sums`
                # has tenth of the target production, divide the target installation by ten).
                # TODO: make sure this allows production variability when we support multiple years.
                key: str = get_basic_key(source)
                if key in base_data_sums:
                    base_production_twh: float = base_data_sums[key] / 1e6
                    production_scale_factor: float = base_production_twh / production_twh
                else:
                    production_scale_factor = 1
                base_installed_gw_map[source] = installed_gw * production_scale_factor
        return base_installed_gw_map

    def get_load_factors(self,
                         scenario: str,
                         target_year: int,
                         country: Zone) -> LoadFactors:
        assert self._entsoe_loader, "ENTSO-E loader is required to calculate load factors"
        assert self._pecd_loader, "PECD loader is required to calculate load factors"

        def _get_yearly_demand(entsoe_year, pecd_year, common_year):
            base_country_demand: Optional[pandas.Series] = (
                self._pecd_loader.load_demand(country, pecd_year, common_year)
                if self._load_demand_from_pecd else None
            )
            if base_country_demand is None:
                df = self._entsoe_loader.load_country_year_data(
                    country, entsoe_year, common_year)
                if df.empty:
                    raise Exception(f"Entsoe data for {country} and {entsoe_year} missing")
                base_country_demand = df[Keys.LOAD]
            return base_country_demand.sum() / 1e3

        # Return the average demand for all the given years.
        base_country_demand_gwh = 0
        for (entsoe_year, pecd_year, common_year) in zip(self._entsoe_years, self._pecd_years, self._common_years):
            base_country_demand_gwh += _get_yearly_demand(entsoe_year, pecd_year, common_year)
        base_country_demand_gwh /= len(self._entsoe_years)

        return load_load_factors_from_ember_ng(
            self._df_sources,
            self._df_demand,
            base_country_demand_gwh,
            scenario=scenario,
            tyndp_base_scenario_and_year=EmberNgLoader.TYNDP_BASE_SCENARIO,
            tyndp_target_scenario_and_year=EmberNgLoader.TYNDP_TARGET_SCENARIO,
            base_year=self._base_year,
            target_year=target_year,
            country=self._map_to_ember_region(country))

    def get_flexible_sources(self,
                             scenario: str,
                             year: int,
                             country: Zone,
                             allow_capex_optimization: bool = False) -> dict[FlexibleSourceType, dict]:
        return load_flexible_sources_from_ember_ng(self._df_sources,
                                                   scenario=scenario,
                                                   year=year,
                                                   country=self._map_to_ember_region(country),
                                                   allow_capex_optimization=allow_capex_optimization)

    def get_interconnectors(self,
                            scenario: str,
                            year: int,
                            countries: Optional[Collection[Zone]] = None,
                            aggregate_countries: Optional[Collection[AggregateRegion]] = None) \
            -> InterconnectorsDict:
        interconnectors = load_interconnectors_from_ember_ng(
            self._df_intercon,
            scenario=scenario,
            year=year,
            base_year=self._base_year,
            countries={self._map_to_ember_region(c) for c in countries} if countries else None)

        # Rename the Ember region names back to our names.
        def rename_dict(d: dict[Region, Any], ember_str: str, country: Zone):
            if ember_str in d:
                d[country] = d[ember_str]
                del d[ember_str]
        for country, ember_name in EmberNgLoader._COUNTRY_MAP.items():
            rename_dict(interconnectors, ember_name, country)
            for to_dict in interconnectors.values():
                rename_dict(to_dict, ember_name, country)

        add_distances_type_and_loss_to_interconnectors(interconnectors)

        if aggregate_countries:
            interconnectors = aggregate_interconnectors(interconnectors, aggregate_countries)
        return interconnectors

    def get_storage(self,
                    scenario: str,
                    target_year: int,
                    country: Zone,
                    allow_capex_optimization: bool = False) -> list[dict]:
        storage = load_storage_from_ember_ng(self._df_sources,
                                             scenario=scenario,
                                             year=target_year,
                                             country=self._map_to_ember_region(country),
                                             allow_capex_optimization=allow_capex_optimization,
                                             load_hydro=not self._load_hydro_from_pecd)
        if self._load_hydro_from_pecd:
            if not self._pecd_loader:
                raise ValueError("PECD loader is required for loading hydro storage")
            storage += self._pecd_loader.load_hydro_storage(country)
        return storage

    def get_countries_from_aggregate(
            self,
            scenario: str,
            target_year: int,
            country: AggregateRegion,
            overrides: Optional[dict[Zone, dict[BasicSourceType, Zone]]] = None) \
            -> dict[Zone, dict[str, Any]]:
        if not overrides:
            overrides = {}
        return {part: self.get_country(scenario, target_year, part,
                                       in_aggregate=country,
                                       profile_overrides=overrides.get(part))
                for part in get_aggregated_countries(country)}

    def get_country(self,
                    scenario: str,
                    target_year: int,
                    country: Zone,
                    allow_capex_optimization: bool = False,
                    normalize_pecd: bool = True,
                    in_aggregate: Optional[AggregateRegion] = None,
                    profile_overrides: Optional[dict[BasicSourceType, Zone]] = None) \
            -> dict[str, Any]:
        result = {
            "basic_sources": self.get_basic_sources(scenario, target_year, country,
                                                    allow_capex_optimization,
                                                    profile_overrides=profile_overrides),
            "pecd_normalization_factors": (
                self.get_pecd_normalization_factors(scenario, target_year, country)
                if normalize_pecd else {}
            ),
            "flexible_sources": self.get_flexible_sources(scenario, target_year,
                                                          country, allow_capex_optimization),
            "installed_gw": self.get_installed(scenario, target_year, country),
            "load_factors": self.get_load_factors(scenario, target_year, country),
            "storage": self.get_storage(scenario, target_year, country, allow_capex_optimization)
        }
        if in_aggregate:
            result["in_aggregate"] = in_aggregate
        return result

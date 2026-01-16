"""
Class that computes and tracks yearly stats for a given region.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Optional, Union

import numpy as np
import pandas as pd

from . import grid_plot_utils
from .country_grid import CountryGrid
from .grid_capex_utils import (
    get_charging_opex_per_mwh_eur, get_discharging_opex_per_mwh_eur,
    get_source_capex_per_year_eur, get_source_opex_per_mwh_eur, get_storage_capex_per_year_eur)
from .grid_plot_utils import (
    Keys, get_basic_key, get_charging_key, get_discharging_key, get_flexible_key,
    get_flexible_electricity_equivalent_key, get_ramp_up_key, get_state_of_charge_key)
from .params_library.interconnectors import (
    Interconnector,
    Interconnectors,
    get_expansion_capex_per_year_eur,
    OUTFLOW_CAPACITY_COST_EUR_PER_MWH)
from .region import Region
from .sources.basic_source import FlexibleBasicSource, Source
from .sources.flexible_source import FlexibleSource, FlexibleSourceType
from .sources.storage import StorageUse


class Season(Enum):
    YEAR = "Y"
    SUMMER = "S"
    WINTER = "W"


class StatType(Enum):
    # Only makes sense for the whole year.
    CAPACITY_GW = "capacity_GW"
    CAPACITY_CHARGING_GW = "capacity_charging_GW"
    CAPACITY_PAID_OFF_GW = "capacity_paid_off_GW"
    CAPACITY_CHARGING_PAID_OFF_GW = "capacity_charging_paid_off_GW"

    # Only as aggregate values.
    LOAD_TWH = "load_TWh"
    IMPORT_TWH = "import_TWh"
    EXPORT_TWH = "export_TWh"
    NET_IMPORT_TWH = "net_import_TWh"
    CURTAILMENT_TWH = "curtailment_TWh"

    # Values computed per source.
    PRODUCTION_TWH = "production_TWh"
    PRODUCTION_EL_EQ_TWH = "production_el_eq_TWh"
    PRODUCTION_USED_TWH = "production_used_TWh"
    PRODUCTION_EXCESS_TWH = "production_excess_TWh"
    DISCHARGED_TWH = "discharged_TWh"  # Overlaps with production for grid storage.
    CHARGED_TWH = "charged_TWh"
    INFLOW_TWH = "inflow_TWh"  # Total natural inflow  (e.g. for hydro storage)
    HEAT_PRODUCTION_PJ = "heat_production_PJ"
    PRODUCTION_HOURS = "production_hours"
    """Number of hours during which the source was producing any energy."""

    # Source economics.
    CAPEX_MN_EUR_PER_YEAR = "capex_mn_EUR_per_yr"
    OPEX_MN_EUR = "opex_mn_EUR"
    WHOLESALE_EXPENSES_MN_EUR = "wholesale_expenses_mn_EUR"
    WHOLESALE_REVENUES_MN_EUR = "wholesale_revenues_mn_EUR"
    WHOLESALE_EXPENSES_PPA_MN_EUR = "wholesale_expenses_PPA_mn_EUR"
    AVERAGE_CONSUMER_PRICE = "avg_consumer_price_EUR_per_MWh"
    AVERAGE_PRODUCER_PRICE = "avg_producer_price_EUR_per_MWh"

    CAPACITY_FACTOR = "capacity_factor"
    CAPACITY_FACTOR_CHARGING = "capacity_factor_charging"

    EMISSIONS_MTCO2 = "emissions_MtCO2"

    POWER_SHARE_HIGH_VALUE = "power_share_high_value"
    POWER_SHARE_LOW_VALUE = "power_share_low_value"
    POWER_SHARE_ZERO_VALUE = "power_share_zero_value"


ImportExport = Literal["IMPORT_EXPORT"]
Total = Literal["TOTAL"]
AnySource = Union[Source, ImportExport, Total]
AnySourceKey = Union[str, ImportExport, Total]


@dataclass
class StatValue:
    season: Season
    source: AnySource
    stat: StatType
    val: float


@dataclass
class StatOutput:
    name: str
    region: Region
    season: str
    source: str
    stat: str
    val: float


@dataclass
class StatPlotElement:
    value: float
    label: str
    color: str


def _key(source: AnySource) -> AnySourceKey:
    if source in (CountryGridStats.import_export, CountryGridStats.total):
        return source
    if isinstance(source.type, Enum):
        return source.type.value
    return source.type


class CountryGridStats:
    import_export: ImportExport = "IMPORT_EXPORT"
    total: Total = "TOTAL"

    def __init__(
        self,
        region: Region,
        grid: CountryGrid,
        interconnectors: Optional[Interconnectors],
        name: str,
        import_ppa_price: Optional[float] = None,
        group_colors: bool = False
    ) -> None:
        self.grid = grid
        self.interconnectors = interconnectors

        self._region = region
        self._name = name
        self._import_ppa_price = import_ppa_price

        # Compute extra columns useful for statistics. Modifies data in place.
        grid_plot_utils.split_excess_production(grid.data)

        # Sort flexible sources by OPEX, from the cheapest to the most expensive.
        # TODO: improve this to account for full opex (when `lifetime_hours` is limited).
        if not group_colors:
            grid.flexible_sources = dict(
                sorted(
                    grid.flexible_sources.items(),
                    key=lambda x: x[1].economics.variable_costs_per_mwh_eur
                )
            )
        else:
            # Sort flexible sources by OPEX from the cheapest to the most expensive where sources of
            # the given color appear all at once (i.e. at the appearance of the cheapest source of
            # the given color).
            colors: set[str] = {source.color for source in grid.flexible_sources.values()}
            # Compute minimum variable cost for each color (in a dict keyed by color string).
            flexible_source_color_min_cost: dict[str, float] = {
                color: min({source.economics.variable_costs_per_mwh_eur
                            for source in grid.flexible_sources.values() if source.color == color})
                for color in colors}
            grid.flexible_sources = dict(
                sorted(
                    grid.flexible_sources.items(),
                    key=lambda x: flexible_source_color_min_cost[x[1].color]
                )
            )

        grid.storage = dict(
            sorted(
                grid.storage.items(),
                key=lambda x: x[1].color
            )
        )

        self._dfs = {
            Season.YEAR: self.grid.data,
            Season.WINTER: grid_plot_utils.get_winter_slice(self.grid.data),
            Season.SUMMER: grid_plot_utils.get_summer_slice(self.grid.data),
        }

        # Dictionary to store and retrieve values for individual stat types.
        self._stats: dict[StatType, list[StatValue]] = {type: [] for type in StatType}

        # Compute stats that are independent of season.
        self._compute_source_installed()
        self._compute_interconnector_capex()

        for season in Season:
            self._compute_source_stats(season)
            self._compute_average_prices(season)

    def get_stats_for_logging(self) -> list[StatOutput]:
        def get_annotated_stat(value: StatValue):
            return StatOutput(self._name, self._region, value.season.value, _key(value.source),
                              value.stat.value, value.val)

        return [get_annotated_stat(value) for sublist in self._stats.values() for value in sublist]

    def get_stat_value_if_exists(self,
                                 source: AnySource,
                                 stat: StatType,
                                 season: Season = Season.YEAR) -> Optional[float]:
        for value in self._stats[stat]:
            if value.season == season and _key(value.source) == _key(source):
                return value.val
        return None

    def get_stat_value(self,
                       source: AnySource,
                       stat: StatType,
                       season: Season = Season.YEAR) -> float:
        value = self.get_stat_value_if_exists(source, stat, season)
        assert value is not None, f"{stat.name} for {season.name} and {_key(source)} was not computed, yet"
        return value

    def get_stat_values(self,
                        stat: StatType,
                        season: Season = Season.YEAR) -> list[float]:
        return [value.val for value in self._stats[stat] if value.season == season]

    def get_stat_dict(self,
                      stat: StatType,
                      season: Season = Season.YEAR) -> dict[AnySourceKey, StatValue]:
        return {_key(value.source): value for value in self._stats[stat] if value.season == season}

    def get_stat_plot_elements(self,
                               stat: StatType,
                               season: Season = Season.YEAR) -> list[StatPlotElement]:
        return [StatPlotElement(value.val, value.source.type.value, value.source.color)
                for value in self._stats[stat]
                if value.source != CountryGridStats.total and value.season == season]

    def _store_stat(self,
                    source: AnySource,
                    stat: StatType,
                    value: float,
                    season: Season = Season.YEAR):
        self._stats[stat].append(StatValue(season, source, stat, value))

    def _compute_average_prices(self, season: Season) -> None:
        df = self._dfs[season]

        # Consumer prices (weighted by demand).
        avg_consumer_price = np.average(df[Keys.PRICE], weights=df[Keys.LOAD])
        self._store_stat(
            CountryGridStats.total, StatType.AVERAGE_CONSUMER_PRICE, avg_consumer_price, season
        )

        # Producer prices (weighted by production).
        avg_producer_price = np.average(df[Keys.PRICE], weights=df[Keys.PRODUCTION])
        self._store_stat(
            CountryGridStats.total, StatType.AVERAGE_PRODUCER_PRICE, avg_producer_price, season
        )

    def _compute_ramp_up_costs(self, source: Source, data: pd.DataFrame) -> float:
        """
        Compute total ramp-up costs of given source if available.
        Returns costs in millions of EUR.
        """
        ramp_up_key = get_ramp_up_key(source.type)
        if ramp_up_key not in data.columns:
            # Ramp-up costs were not optimized for so we ignore them
            # for costs computation.
            return 0

        # Non-flexible sources shouldn't be capable of ramping.
        assert isinstance(source, (FlexibleBasicSource, FlexibleSource))
        return (data[ramp_up_key] * source.ramp_up_cost_mw_eur).sum() / 1e6

    def _compute_source_installed(self):
        for source in self.grid.basic_sources.values():
            self._store_stat(source, StatType.CAPACITY_GW, source.capacity_mw / 1000)
            self._store_stat(source, StatType.CAPACITY_PAID_OFF_GW,
                             source.paid_off_capacity_mw / 1000)

        for source in self.grid.flexible_sources.values():
            if source.virtual:
                continue

            self._store_stat(source, StatType.CAPACITY_GW,
                                source.capacity_mw / 1000)
            self._store_stat(source, StatType.CAPACITY_PAID_OFF_GW,
                                source.paid_off_capacity_mw / 1000)

        for source in self.grid.storage.values():
            self._store_stat(source, StatType.CAPACITY_CHARGING_GW,
                             source.capacity_mw_charging / 1000)
            self._store_stat(source, StatType.CAPACITY_GW,
                             source.capacity_mw / 1000)
            self._store_stat(source, StatType.CAPACITY_PAID_OFF_GW,
                             source.paid_off_capacity_mw / 1000)
            self._store_stat(source, StatType.CAPACITY_CHARGING_PAID_OFF_GW,
                             source.paid_off_capacity_mw_charging / 1000)

        self._store_stat(CountryGridStats.total, StatType.CAPACITY_GW,
                         sum(self.get_stat_values(StatType.CAPACITY_GW)))

    def _compute_interconnector_capex(self) -> None:
        if not self.interconnectors:
            return

        dict_from: dict[Region, Interconnector] = self.interconnectors.get_connections_from(
            self._region)
        dict_to: dict[Region, Interconnector] = self.interconnectors.get_connections_to(
            self._region)
        neighbors = dict_from.keys() | dict_to.keys()
        total_capex_mn_eur = 0
        for neighbor in neighbors:
            # Both directions present. Assume this is anyway one connection, take average expansion.
            if neighbor in dict_from and neighbor in dict_to:
                i_from = dict_from[neighbor]
                i_to = dict_to[neighbor]
                assert i_to.length_km == i_from.length_km
                length_km = i_to.length_km
                assert i_to.type == i_from.type
                type = i_to.type
                upgrade_mw_from = i_from.capacity_mw - i_from.paid_off_capacity_mw
                upgrade_mw_to = i_to.capacity_mw - i_to.paid_off_capacity_mw
                upgrade_mw = (upgrade_mw_from + upgrade_mw_to) / 2
            else:
                i = dict_from[neighbor] if neighbor in dict_from else dict_to[neighbor]
                length_km = i.length_km
                upgrade_mw = i.capacity_mw - i.paid_off_capacity_mw
                type = i.type

            # Assume each country pays half of the costs.
            country_length_km = length_km / 2
            country_capex_eur = get_expansion_capex_per_year_eur(
                upgrade_mw, country_length_km, type=type)
            total_capex_mn_eur += country_capex_eur / 1e6

        self._store_stat(CountryGridStats.import_export,
                         StatType.CAPEX_MN_EUR_PER_YEAR,
                         total_capex_mn_eur)

    def _compute_source_stats(self, season: Season) -> None:
        df = self._dfs[season]
        df_sum_twh_per_year = df.sum() / 1_000_000 / self.grid.num_years

        self._compute_load(season, df_sum_twh_per_year)
        self._compute_curtailment(season, df)
        self._compute_import_export(season, df_sum_twh_per_year)

        self._compute_production(season, df_sum_twh_per_year)
        self._compute_production_hours(season, df)
        self._compute_capacity_factor(season, len(df.index) / self.grid.num_years)
        self._compute_emissions(season)
        self._compute_costs(season, df)

        storable_MW, curtailment_MW, shortage_MW = \
            grid_plot_utils.get_storable_curtailment_shortage(df)
        self._compute_power_share(season, storable_MW, curtailment_MW, shortage_MW)

    def _compute_costs(self, season: Season, data: pd.DataFrame):
        def _get_total_price_mn_eur(key: str):
            return (data[Keys.PRICE] * data[key]).sum() / 1e6 / self.grid.num_years

        for basic_source in self.grid.basic_sources.values():
            key = get_basic_key(basic_source.type)
            total_mwh = 1e6 * self.get_stat_value(basic_source, StatType.PRODUCTION_TWH, season)
            capex_mn_eur = get_source_capex_per_year_eur(basic_source) / 1e6
            opex_eur_per_mwh = get_source_opex_per_mwh_eur(basic_source, total_mwh)
            opex_mn_eur = opex_eur_per_mwh * total_mwh / 1e6
            total_price_mn_eur = _get_total_price_mn_eur(key)

            # Add ramp-up costs to opex if source is ramped.
            opex_mn_eur += self._compute_ramp_up_costs(basic_source, data)

            self._store_stat(basic_source, StatType.CAPEX_MN_EUR_PER_YEAR, capex_mn_eur, season)
            self._store_stat(basic_source, StatType.OPEX_MN_EUR, opex_mn_eur, season)
            self._store_stat(basic_source, StatType.WHOLESALE_REVENUES_MN_EUR,
                             total_price_mn_eur, season)

        for flexible_source in self.grid.flexible_sources.values():
            if flexible_source.virtual:
                continue

            key = get_flexible_key(flexible_source)

            total_mwh = 1e6 * self.get_stat_value(flexible_source, StatType.PRODUCTION_TWH, season)
            capex_mn_eur = get_source_capex_per_year_eur(flexible_source) / 1e6
            opex_eur_per_mwh = get_source_opex_per_mwh_eur(flexible_source, total_mwh)
            opex_mn_eur = opex_eur_per_mwh * total_mwh / 1e6
            total_price_mn_eur = _get_total_price_mn_eur(key)

            # Add ramp-up costs to opex if source is ramped.
            opex_mn_eur += self._compute_ramp_up_costs(flexible_source, data)

            self._store_stat(flexible_source, StatType.CAPEX_MN_EUR_PER_YEAR, capex_mn_eur, season)
            self._store_stat(flexible_source, StatType.OPEX_MN_EUR, opex_mn_eur, season)
            self._store_stat(flexible_source, StatType.WHOLESALE_REVENUES_MN_EUR,
                             total_price_mn_eur, season)

        for storage in self.grid.storage.values():
            state_of_charge_key = get_state_of_charge_key(storage)
            charging_key = get_charging_key(storage)
            discharging_key = get_discharging_key(storage)
            sell_revenue_mn_eur = _get_total_price_mn_eur(discharging_key)
            buy_expenses_mn_eur = _get_total_price_mn_eur(charging_key)

            total_mwh_discharged = 1e6 * \
                self.get_stat_value(storage, StatType.DISCHARGED_TWH, season)
            total_mwh_charged = 1e6 * self.get_stat_value(storage, StatType.CHARGED_TWH, season)
            capex_mn_eur = get_storage_capex_per_year_eur(storage) / 1e6
            discharging_opex_eur_per_mwh = get_discharging_opex_per_mwh_eur(
                storage, total_mwh_discharged)
            charging_opex_eur_per_mwh = get_charging_opex_per_mwh_eur(storage, total_mwh_charged)
            opex_mn_eur = (discharging_opex_eur_per_mwh * total_mwh_discharged / 1e6 +
                           charging_opex_eur_per_mwh * total_mwh_charged / 1e6)

            # Substract gains from extra state of charge (e.g. selling hydrogen) / add costs
            # from missing state of charge (e.g. buying imported hydrogen) per year.
            final_state_mwh = data[state_of_charge_key].iat[-1]
            target_final_state_mwh = storage.final_energy_mwh
            # For separate charging, the bounds get multiplied by number of years.
            if storage.separate_charging:
                target_final_state_mwh *= self.grid.num_years
            extra_state_mwh = final_state_mwh - target_final_state_mwh
            # Substract these gains from OPEX (or add extra costs to opex), average value per year.
            total_gains_mn_eur = (extra_state_mwh * storage.cost_sell_buy_mwh_eur) / 1e6
            opex_mn_eur -= total_gains_mn_eur / self.grid.num_years

            self._store_stat(storage, StatType.CAPEX_MN_EUR_PER_YEAR, capex_mn_eur, season)
            self._store_stat(storage, StatType.OPEX_MN_EUR, opex_mn_eur, season)
            self._store_stat(storage, StatType.WHOLESALE_EXPENSES_MN_EUR, buy_expenses_mn_eur,
                             season)
            self._store_stat(storage, StatType.WHOLESALE_REVENUES_MN_EUR, sell_revenue_mn_eur,
                             season)

        # Compute total export revenues and import costs.
        # TODO: Should the export/import prices be different from
        # the spot in the country of origin?
        net_export = -data[Keys.NET_IMPORT].clip(upper=0)
        export_revenues_mn_eur = (
            # Charge the exporting party with interconnection costs.
            net_export * (data[Keys.PRICE] - OUTFLOW_CAPACITY_COST_EUR_PER_MWH)
        ).sum() / 1e6 / self.grid.num_years
        self._store_stat(CountryGridStats.import_export, StatType.WHOLESALE_REVENUES_MN_EUR,
                         export_revenues_mn_eur, season)

        net_import = data[Keys.NET_IMPORT].clip(lower=0)
        import_costs_mn_eur = (
            net_import * data[Keys.PRICE]
        ).sum() / 1e6 / self.grid.num_years
        self._store_stat(CountryGridStats.import_export, StatType.WHOLESALE_EXPENSES_MN_EUR,
                         import_costs_mn_eur, season)

        # Compute import/export revenues and costs assuming PPA-like pricing.
        # if self._import_ppa_price:
        #     export_revenues_ppa_mn_eur = (
        #         -data[Keys.NET_IMPORT].clip(upper=0) *
        #         data[Keys.PRICE_EXPORT].clip(lower=self._import_ppa_price)
        #     ).sum() / 1e6 / self.grid.num_years
        #     self._store_stat(CountryGridStats.import_export,
        #                      StatType.WHOLESALE_REVENUES_PPA_MN_EUR,
        #                      export_revenues_ppa_mn_eur, season)

        #     import_costs_ppa_mn_eur = (
        #         data[Keys.NET_IMPORT].clip(lower=0) *
        #         data[Keys.PRICE_IMPORT].clip(lower=self._import_ppa_price)
        #     ).sum() / 1e6 / self.grid.num_years
        #     self._store_stat(CountryGridStats.import_export,
        #                      StatType.WHOLESALE_EXPENSES_PPA_MN_EUR,
        #                      import_costs_ppa_mn_eur, season)

    def _compute_load(self, season: Season, df_sum_twh: pd.Series):
        self._store_stat(CountryGridStats.total, StatType.LOAD_TWH,
                         df_sum_twh[grid_plot_utils.Keys.LOAD], season)

    def _compute_curtailment(self, season: Season, df: pd.DataFrame):
        total_curtailment_twh = df["Curtailment"].clip(
            lower=0).sum() / 1_000_000 / self.grid.num_years
        self._store_stat(CountryGridStats.total, StatType.CURTAILMENT_TWH,
                         total_curtailment_twh, season)

    def _compute_import_export(self, season: Season, df_sum_twh: pd.Series):
        import_twh = df_sum_twh[grid_plot_utils.Keys.IMPORT]
        export_twh = df_sum_twh[grid_plot_utils.Keys.EXPORT]
        self._store_stat(CountryGridStats.total, StatType.IMPORT_TWH, import_twh, season)
        self._store_stat(CountryGridStats.total, StatType.EXPORT_TWH, export_twh, season)
        self._store_stat(CountryGridStats.total, StatType.NET_IMPORT_TWH,
                         import_twh - export_twh, season)

    def _compute_production(self, season: Season, df_sum_twh: pd.Series):
        for type, source in self.grid.basic_sources.items():
            twh = df_sum_twh[grid_plot_utils.get_basic_key(type)]
            self._store_stat(source, StatType.PRODUCTION_TWH, twh, season)

            used_key = grid_plot_utils.get_basic_used_key(type)
            if used_key in df_sum_twh:
                used_twh = df_sum_twh[used_key]
                self._store_stat(
                    source, StatType.PRODUCTION_USED_TWH, used_twh, season)
                excess_twh = df_sum_twh[grid_plot_utils.get_basic_excess_key(type)]
                self._store_stat(
                    source, StatType.PRODUCTION_EXCESS_TWH, excess_twh, season)

        for source in self.grid.flexible_sources.values():
            total_twh = df_sum_twh[grid_plot_utils.get_flexible_key(source)]
            self._store_stat(source, StatType.PRODUCTION_TWH, total_twh, season)

            if source.heat:
                total_el_eq_twh = \
                    df_sum_twh[grid_plot_utils.get_flexible_electricity_equivalent_key(source)]
                self._store_stat(source, StatType.PRODUCTION_EL_EQ_TWH, total_el_eq_twh, season)

                heat_key = grid_plot_utils.get_flexible_heat_key(source)
                # Convert terawatthours to petajoules.
                total_heat_pj = 3.6 * df_sum_twh.get(heat_key, 0.0)
                self._store_stat(source, StatType.HEAT_PRODUCTION_PJ, total_heat_pj, season)

        for source in self.grid.storage.values():
            twh_discharging = df_sum_twh[grid_plot_utils.get_discharging_key(source)]
            self._store_stat(source, StatType.PRODUCTION_TWH, twh_discharging, season)
            self._store_stat(source, StatType.DISCHARGED_TWH, twh_discharging, season)
            twh_charging = df_sum_twh[grid_plot_utils.get_charging_key(source)]
            self._store_stat(source, StatType.CHARGED_TWH, twh_charging, season)
            if source.inflow_hourly_data_key:
                twh_inflow = df_sum_twh[source.inflow_hourly_data_key]
                self._store_stat(source, StatType.INFLOW_TWH, twh_inflow, season)

        self._store_stat(CountryGridStats.total, StatType.PRODUCTION_TWH,
                         sum(self.get_stat_values(StatType.PRODUCTION_TWH)), season)
        self._store_stat(CountryGridStats.total, StatType.DISCHARGED_TWH,
                         sum(self.get_stat_values(StatType.DISCHARGED_TWH)), season)
        self._store_stat(CountryGridStats.total, StatType.CHARGED_TWH,
                         sum(self.get_stat_values(StatType.CHARGED_TWH)), season)

    def _compute_production_hours(self, season: Season, df: pd.DataFrame):
        for source in self.grid.flexible_sources.values():
            key = grid_plot_utils.get_flexible_key(source)
            # Only count production of more than 1 kWh.
            total_hours = (df[key] > 1e-3).sum()
            self._store_stat(source, StatType.PRODUCTION_HOURS, total_hours, season)

        for source in self.grid.storage.values():
            key = grid_plot_utils.get_discharging_key(source)
            # Only count production of more than 1 kWh.
            total_hours = (df[key] > 1e-3).sum()
            self._store_stat(source, StatType.PRODUCTION_HOURS, total_hours, season)

    def _compute_capacity_factor(self, season: Season, total_hours: float) -> None:
        self._compute_capacity_factor_impl(
            season, total_hours, StatType.PRODUCTION_TWH, StatType.CAPACITY_GW,
            StatType.CAPACITY_FACTOR)
        self._compute_capacity_factor_impl(
            season, total_hours, StatType.CHARGED_TWH, StatType.CAPACITY_CHARGING_GW,
            StatType.CAPACITY_FACTOR_CHARGING)

    def _compute_capacity_factor_impl(self,
                                      season: Season,
                                      total_hours: float,
                                      production_type: StatType,
                                      capacity_type: StatType,
                                      factor_type: StatType) -> None:
        capacities_gw = self.get_stat_dict(capacity_type, Season.YEAR)
        productions_twh = self.get_stat_dict(production_type, season)
        productions_el_eq_twh = self.get_stat_dict(StatType.PRODUCTION_EL_EQ_TWH, season)

        # This includes the aggregate value.
        for key, capacity_gw in capacities_gw.items():
            source = capacity_gw.source
            if capacity_gw.val == 0 or key not in productions_twh:
                continue
            production_twh = productions_twh[key]
            if key in productions_el_eq_twh:
                production_twh = productions_el_eq_twh[key]
            assert source == production_twh.source, "source types must be unique"
            factor = production_twh.val * 1_000 / (capacity_gw.val * total_hours)
            self._store_stat(source, factor_type, factor, season)

    def _compute_emissions(self, season: Season) -> None:
        power_twh = self.get_stat_dict(StatType.PRODUCTION_TWH, season)
        el_eq_twh = self.get_stat_dict(StatType.PRODUCTION_EL_EQ_TWH, season)

        for key, stat in power_twh.items():
            # This excludes the aggregate value.
            if key in (CountryGridStats.import_export, CountryGridStats.total):
                continue

            source = stat.source
            production_twh = stat.val
            # Include emissions from heat production in the case of CHP.
            if key in el_eq_twh:
                production_twh = el_eq_twh[key].val
            # TODO: Include extra emissions from ramp ups. This will require
            # passing the ramping fuel consumption and efficiency/emission intensity
            # further through the data flow.
            # t per MWh = Mt per TWh.
            co2_Mt = production_twh * source.co2_t_mwh
            self._store_stat(source, StatType.EMISSIONS_MTCO2, co2_Mt, season)

        total_emissions_mt_co2eq = sum(self.get_stat_values(StatType.EMISSIONS_MTCO2))
        self._store_stat(CountryGridStats.total, StatType.EMISSIONS_MTCO2,
                         total_emissions_mt_co2eq, season)

    def _compute_power_share(self,
                             season: Season,
                             storable_MW: pd.DataFrame,
                             curtailment_MW: pd.DataFrame,
                             shortage_MW: pd.DataFrame) -> None:
        for type, source in self.grid.basic_sources.items():
            total_twh = self.get_stat_value(source, StatType.PRODUCTION_TWH, season)
            if total_twh == 0:
                self._store_stat(source, StatType.POWER_SHARE_ZERO_VALUE, 0, season)
                self._store_stat(source, StatType.POWER_SHARE_LOW_VALUE, 0, season)
                self._store_stat(source, StatType.POWER_SHARE_HIGH_VALUE, 1, season)
                continue

            source_key = grid_plot_utils.get_basic_key(type)
            zero_twh = curtailment_MW[source_key].sum() / 1_000_000 / self.grid.num_years
            low_twh = storable_MW[source_key].sum() / 1_000_000 / self.grid.num_years
            high_twh = shortage_MW[source_key].sum() / 1_000_000 / self.grid.num_years

            self._store_stat(
                source, StatType.POWER_SHARE_ZERO_VALUE, zero_twh / total_twh, season)
            self._store_stat(
                source, StatType.POWER_SHARE_LOW_VALUE, low_twh / total_twh, season)
            self._store_stat(
                source, StatType.POWER_SHARE_HIGH_VALUE, high_twh / total_twh, season)

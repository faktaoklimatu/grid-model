"""
Provides estimates of grid spot prices.
"""

import math

import pandas as pd

from .grid_capex_utils import *
from .country_grid import CountryGrid
from .grid_plot_utils import (
    Keys,
    get_flexible_electricity_equivalent_key,
    get_flexible_heat_key,
    has_curtailment,
    has_excess,
    get_basic_key,
    get_charging_key,
    get_discharging_key,
    get_flexible_key,
)
from .sources.heat_source import BackPressureTurbine, ExtractionTurbine, HeatRecoveryUnit
from .sources.storage import StorageType, StorageUse, Storage

# Crude heuristic estimate and simplification of the economics of
# hydro based on observations from the Norwegian electricity market
# where hydro is the dominant source and is often exported.
FLEXIBLE_HYDRO_ASK_PRICE = 20
FLEXIBLE_HYDRO_TYPES = (StorageType.PUMPED_OPEN, StorageType.RESERVOIR)
# Inflexible hydro must run whenever there's water (as it often has no
# regulation capabilities) and thus cannot determine the market price.
# (It _mostly_ gets a higher closing price due to more expensive sources
# generating at the margin.)
INFLEXIBLE_HYDRO_ASK_PRICE = 0
INFLEXIBLE_HYDRO_TYPES = (StorageType.ROR,)

# A crude heuristic that puts a ceiling on what storage is willing to pay for excess renewable
# electricity.
# TODO: Implement a better algorithmic estimate that is context-based and works well with market
# coupling. Some thoughts:
# - if, on that day, all available short-term storage capacity is fully charged & flexibility is
# fully used, storage prices should be zero all the time
# - if, on the other hand, there is competition for the excess RES electricity, prices might
# converge to {what the facility earns in the next cycle} / {efficiency} - {O&M}.
STORAGE_CHARGING_MAX_PRICE = 5


class CountryGridSpotPriceEstimator:
    def __init__(
        self,
        grid: CountryGrid
    ) -> None:
        self.grid = grid

    def _maybe_update_price(self,
                            row: pd.Series,
                            current: tuple[float, str],
                            candidate: tuple[float, str],
                            max: bool = True) -> tuple[float, str]:
        price, key = candidate

        should_update = price > current[0] if max else price < current[0]

        if row[key] > 1e-3 and should_update:
            return candidate
        return current

    def estimate_spot_price(self, row: pd.Series, import_price: float) -> tuple[float, str]:
        maximum: tuple[float, str] = 0, "Curtailment"
        # No discussion about positive price if there is non-negligible curtailment.
        if has_curtailment(row):
            return maximum

        # Basic or flexible sources do not dictate the price if there is excess, this is dictated
        # by demand side.
        minimum_storage_price = 5
        if has_excess(row):
            return minimum_storage_price, "Charging_min"

        maximum = self._maybe_update_price(row, maximum, (import_price, Keys.NET_IMPORT))

        # TODO: Include amortization based on capex, lifetime and realized capacity factor.
        min_flexible_price = min(
            source.economics.variable_costs_per_mwh_eur
            for source in self.grid.flexible_sources.values()
        )

        for type, source in self.grid.basic_sources.items():
            maximum = self._maybe_update_price(
                row, maximum, (source.economics.variable_costs_per_mwh_eur, get_basic_key(type)))
        for source in self.grid.flexible_sources.values():
            heat_key = get_flexible_heat_key(source)
            if isinstance(source.heat, ExtractionTurbine) and source.heat.min_ratio_el > 0 and heat_key in row:
                # Skip this source if it has an extraction turbine and
                # generates only the least permissible amount of electricity.
                heat_MW = row[heat_key]
                if heat_MW > 1e-3:
                    total_el_eq_MW = row[get_flexible_electricity_equivalent_key(source)]
                    electricity_MW = row[get_flexible_key(source)]
                    if abs(electricity_MW - source.heat.min_ratio_el * total_el_eq_MW) <= 1e-3:
                        continue
            elif isinstance(source.heat, HeatRecoveryUnit) and source.heat.max_heat_mw_per_el_mw:
                # Similarly, skip if the heat recovery unit is running
                # at full capacity.
                heat_MW = row[heat_key]
                if heat_MW > 1e-3:
                    electricity_MW = row[get_flexible_key(source)]
                    if abs(heat_MW - source.heat.max_heat_mw_per_el_mw * electricity_MW) <= 1e-3:
                        continue
            elif isinstance(source.heat, BackPressureTurbine):
                # Skip all must-run back-pressure turbines.
                continue

            # TODO: Add ramp up costs.
            maximum = self._maybe_update_price(
                row, maximum, (source.economics.variable_costs_per_mwh_eur, get_flexible_key(source)))

        for storage in self.grid.storage.values():
            if storage.use.is_electricity():
                if storage.type in INFLEXIBLE_HYDRO_TYPES:
                    price = INFLEXIBLE_HYDRO_ASK_PRICE
                elif storage.type in FLEXIBLE_HYDRO_TYPES:
                    price = FLEXIBLE_HYDRO_ASK_PRICE
                else:
                    # Assume storage discharging always asks at zero and gets
                    # remuneration from much higher closing price.
                    price = min_flexible_price

                # If this storage cannot charge (but can buy energy, such as H2), adjust its
                # ask price accordingly.
                if storage.capacity_mw_charging == 0 and storage.cost_sell_buy_mwh_eur > 0:
                    variable_cost_per_mwh_eur: float = storage.cost_sell_buy_mwh_eur / storage.discharging_efficiency
                    price = max(price, variable_cost_per_mwh_eur)

                maximum = self._maybe_update_price(
                    row, maximum, (price, get_discharging_key(storage)))

        return maximum

    def estimate_spot_price_with_charging(
            self,
            row: pd.Series,
            maximum: tuple[float, str],
            storage_average_margin_per_mwh: dict[StorageType, float]) -> tuple[float, str]:
        # No discussion about positive price if there is non-negligible curtailment.
        if has_curtailment(row):
            return maximum

        def get_buy_price(storage: Storage) -> float:
            margin = storage_average_margin_per_mwh[storage.type]
            return max(0, margin)

        # Search for the _minimum_ price of used storage and update max if this minimum is above max.
        min: tuple[float, str] = math.inf, "Infty"
        for storage in self.grid.storage.values():
            if storage.use == StorageUse.ELECTRICITY:
                buy_price = get_buy_price(storage)
                min = self._maybe_update_price(
                    row, min, (buy_price, get_charging_key(storage)), max=False)
        if min[0] < math.inf:
            maximum = self._maybe_update_price(row, maximum, min)

        return maximum

    def compute_storage_average_margin_per_mwh(self) -> dict[StorageType, float]:
        def compute_margin(storage: Storage) -> float:
            total_discharging_mwh = self.grid.data[get_discharging_key(storage)].sum()
            if total_discharging_mwh == 0:
                return 0

            sell_eur = self.grid.data[Keys.PRICE] * self.grid.data[get_discharging_key(storage)]
            price_per_mwh_eur = sell_eur.sum() / total_discharging_mwh

            # Opex for discharging is composed of opex for charging (increased by losses) and opex
            # for discharging.
            total_charging_mwh = self.grid.data[get_charging_key(storage)].sum()
            charging_opex_per_mwh_eur = get_charging_opex_per_mwh_eur(storage, total_charging_mwh)
            round_trip_efficiency = storage.charging_efficiency * storage.discharging_efficiency
            opex_per_mwh_eur = charging_opex_per_mwh_eur / round_trip_efficiency
            discharging_opex_per_mwh_eur = get_discharging_opex_per_mwh_eur(
                storage, total_discharging_mwh)
            opex_per_mwh_eur += discharging_opex_per_mwh_eur

            margin = (price_per_mwh_eur - opex_per_mwh_eur) * round_trip_efficiency
            # TODO: improve the algorithm (see the comment at STORAGE_CHARGING_MAX_PRICE).
            return min(STORAGE_CHARGING_MAX_PRICE, margin)

        return {
            key: compute_margin(storage)
            for key, storage in self.grid.storage.items()
            if storage.use.is_electricity()
        }

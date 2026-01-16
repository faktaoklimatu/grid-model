"""
Provides util functions for computing capex costs for grid technologies.
"""

from typing import Optional, Union

import pulp

from .sources.basic_source import Source
from .sources.economics import SourceEconomics
from .sources.storage import Storage, StorageUse


MaybeAffineExpression = Union[float, pulp.LpAffineExpression]


def _get_dicounted_activity_length(discount_rate: float,
                                   delay_years: float,
                                   activity_years: float):
    def negative_exponential_series_sum(base: float,
                                        exponent: float,
                                        length: float):
        if length > 100:
            # Approximate length by \infty.
            return (base ** exponent) / (1 - (1 / base))

        if length == 0:
            return 0
        elif length < 1:
            return length * (base ** exponent)
        return base ** exponent + negative_exponential_series_sum(base, exponent - 1, length - 1)

    return negative_exponential_series_sum(discount_rate, -1 * delay_years, activity_years)


def _get_investment_costs_per_year_eur(capacity_mw: MaybeAffineExpression,
                                       overnight_costs_per_kw_eur: float,
                                       decommissioning_cost_per_kw_eur: float,
                                       construction_time_years: int,
                                       lifetime_years: float,
                                       decommissioning_time_years: int,
                                       discount_rate: float) -> MaybeAffineExpression:
    # In the first year of construction, average time capital is needed is 0.5 years.
    initial_delay = 0.5
    construction_discounted_years = _get_dicounted_activity_length(
        discount_rate, initial_delay, construction_time_years)
    lifetime_discounted_years = _get_dicounted_activity_length(
        discount_rate, initial_delay + construction_time_years, lifetime_years)
    decommissioning_discounted_years = _get_dicounted_activity_length(
        discount_rate, initial_delay + construction_time_years + lifetime_years,
        decommissioning_time_years)

    construction_costs_per_year = overnight_costs_per_kw_eur / construction_time_years
    construction_costs_per_kw_eur = construction_discounted_years * construction_costs_per_year
    decommissioning_costs_per_year = decommissioning_cost_per_kw_eur / decommissioning_time_years
    decommissioning_costs_per_kw_eur = decommissioning_discounted_years * decommissioning_costs_per_year

    capacity_kw = capacity_mw * 1000
    lifetime_costs = capacity_kw * (construction_costs_per_kw_eur +
                                    decommissioning_costs_per_kw_eur)
    return lifetime_costs / lifetime_discounted_years


def _get_source_economics_investment_costs_per_year_eur(
        economics: SourceEconomics,
        capacity_mw: MaybeAffineExpression,
        production_mwh: Optional[float] = None) -> MaybeAffineExpression:
    lifetime_years = economics.lifetime_years
    # Adjust lifetime years based on real usage (if available):
    if economics.lifetime_hours is not None and production_mwh is not None and production_mwh > 0:
        production_hours = production_mwh / capacity_mw
        lifetime_years = economics.lifetime_hours / production_hours

    return _get_investment_costs_per_year_eur(capacity_mw, economics.overnight_costs_per_kw_eur,
                                              economics.decommissioning_cost_per_kw_eur,
                                              economics.construction_time_years,
                                              lifetime_years,
                                              economics.decommissioning_time_years,
                                              economics.discount_rate)


def _get_source_economics_fixed_o_m_costs_per_year_eur(
        economics: SourceEconomics,
        capacity_mw: MaybeAffineExpression) -> MaybeAffineExpression:
    capacity_kw = capacity_mw * 1000
    return capacity_kw * economics.fixed_o_m_costs_per_kw_eur


def _get_source_economics_capex_per_year_eur(
        economics: SourceEconomics,
        capacity_mw: MaybeAffineExpression) -> MaybeAffineExpression:
    capex_per_year_eur = _get_source_economics_fixed_o_m_costs_per_year_eur(economics, capacity_mw)

    # If lifetime is specified in hours, it's treated as part of opex (and not computed here).
    if economics.lifetime_hours is None:
        capex_per_year_eur += _get_source_economics_investment_costs_per_year_eur(
            economics, capacity_mw)

    return capex_per_year_eur


def get_source_capex_per_year_eur_with_capacity(
        source: Source,
        capacity_mw: MaybeAffineExpression) -> MaybeAffineExpression:
    # This code path ignores `source.paid_off_capacity_mw` as it is more complicated than a simple
    # subtraction and it is anyway irrelevant for the optimization (subtracting a constant).
    return _get_source_economics_capex_per_year_eur(source.economics, capacity_mw)


def get_source_capex_per_year_eur(source: Source) -> float:
    # Subtract capacity that is already payed off.
    newly_built_capacity_mw: float = source.capacity_mw - source.paid_off_capacity_mw
    return _get_source_economics_capex_per_year_eur(source.economics, newly_built_capacity_mw)


def get_storage_capex_per_year_eur_with_capacities(
        storage: Storage,
        discharging_mw: MaybeAffineExpression,
        charging_mw: MaybeAffineExpression) -> MaybeAffineExpression:
    # This code path ignores `storage.paid_off_capacity_mw` and
    # `storage.paid_off_capacity_mw_charging` as it is more complicated than a simple subtraction
    # and it is anyway irrelevant for the optimization (subtracting a constant).
    if storage.use == StorageUse.POWER_TO_HEAT:
        # Capex for power-to-heat is based on the charging capacity only.
        # FIXME: Assumes power → heat direction only. Do we want to
        # support heat-to-power as well?
        return _get_source_economics_capex_per_year_eur(storage.economics, charging_mw)

    capex = _get_source_economics_capex_per_year_eur(storage.economics, discharging_mw)
    if storage.separate_charging is not None:
        capex += _get_source_economics_capex_per_year_eur(storage.separate_charging, charging_mw)
    return capex


def get_storage_capex_per_year_eur(storage: Storage) -> float:
    newly_built_capacity_mw: float = storage.capacity_mw - storage.paid_off_capacity_mw
    newly_built_capacity_mw_charging: float = storage.capacity_mw_charging - storage.paid_off_capacity_mw_charging
    return get_storage_capex_per_year_eur_with_capacities(
        storage, newly_built_capacity_mw, newly_built_capacity_mw_charging)


def _get_source_economics_opex_per_mwh_eur(economics: SourceEconomics,
                                           capacity_mw: MaybeAffineExpression,
                                           production_mwh: Optional[float]) -> MaybeAffineExpression:
    opex_eur = economics.variable_costs_per_mwh_eur
    # If lifetime is specified in hours, investment costs are treated as part of opex (and not
    # counted in capex).
    if economics.lifetime_hours is not None:
        if production_mwh is not None and production_mwh > 0:
            investment_costs_per_year_eur = _get_source_economics_investment_costs_per_year_eur(
                economics, capacity_mw, production_mwh)
            opex_eur += investment_costs_per_year_eur / production_mwh
        else:
            # Compute costs per MW of capacity (this avoids dividing by non-constant `capacity_mw`
            # in computing `opex_eur` below).
            investment_costs_per_year_per_mw_eur = _get_source_economics_investment_costs_per_year_eur(
                economics, capacity_mw=1)
            # If real usage is not available (such as before optimization), specified lifetime_years
            # is used as a proxy and the yearly costs are divided by a fair share of usage hours.
            # As a result if the actual production in e.g. 2x larger than the fair share, costs paid
            # through opex are also 2x larger than `investment_costs_per_year_eur`.
            fair_hours_per_year = economics.lifetime_hours / economics.lifetime_years
            fair_production_per_year_per_mw_mwh = fair_hours_per_year
            opex_eur += investment_costs_per_year_per_mw_eur / fair_production_per_year_per_mw_mwh

    return opex_eur


def get_source_opex_per_mwh_eur_with_capacity(source: Source,
                                              capacity_mw: MaybeAffineExpression,
                                              production_mwh: Optional[float] = None) -> float:
    return _get_source_economics_opex_per_mwh_eur(source.economics, capacity_mw, production_mwh)


def get_source_opex_per_mwh_eur(source: Source,
                                production_mwh: Optional[float] = None) -> float:
    return get_source_opex_per_mwh_eur_with_capacity(source, source.capacity_mw, production_mwh)


def get_discharging_opex_per_mwh_eur_with_capacity(storage: Storage,
                                                   discharging_mw: MaybeAffineExpression,
                                                   discharging_mwh: Optional[float] = None) -> float:
    return _get_source_economics_opex_per_mwh_eur(storage.economics, discharging_mw, discharging_mwh)


def get_discharging_opex_per_mwh_eur(storage: Storage,
                                     discharging_mwh: Optional[float] = None) -> float:
    return get_discharging_opex_per_mwh_eur_with_capacity(
        storage, storage.capacity_mw, discharging_mwh)


def get_charging_opex_per_mwh_eur_with_capacity(storage: Storage,
                                                charging_mw: MaybeAffineExpression,
                                                charging_mwh: Optional[float] = None) -> float:
    if storage.use == StorageUse.POWER_TO_HEAT:
        # Opex of power-to-heat is based on charging only.
        return _get_source_economics_opex_per_mwh_eur(
            storage.economics, charging_mw, charging_mwh)

    if not storage.separate_charging:
        return 0
    return _get_source_economics_opex_per_mwh_eur(
        storage.separate_charging, charging_mw, charging_mwh)


def get_charging_opex_per_mwh_eur(storage: Storage,
                                  charging_mwh: Optional[float] = None) -> float:
    return get_charging_opex_per_mwh_eur_with_capacity(
        storage, storage.capacity_mw_charging, charging_mwh)


def get_interconnector_capex_per_year_eur(capacity_mw: float,
                                          length_km: float,
                                          fixed_o_m_costs_per_mw_per_km_eur: float,
                                          overnight_costs_per_mw_per_km_eur: float,
                                          construction_time_years: int,
                                          lifetime_years: float,
                                          discount_rate: float) -> float:
    o_m_per_year = capacity_mw * fixed_o_m_costs_per_mw_per_km_eur * length_km
    overnight_costs_per_kw = overnight_costs_per_mw_per_km_eur / 1000
    capex_per_year = _get_investment_costs_per_year_eur(capacity_mw,
                                                        overnight_costs_per_kw * length_km,
                                                        decommissioning_cost_per_kw_eur=0,
                                                        construction_time_years=construction_time_years,
                                                        lifetime_years=lifetime_years,
                                                        decommissioning_time_years=1,
                                                        discount_rate=discount_rate)
    return o_m_per_year + capex_per_year

"""
Provides util functions for computing opex costs for grid technologies.
"""

from typing import Callable, Any

def get_flexible_source_cost_params(variable_o_m_per_mwh_el_eur: float,
                                    wear_cost_per_mw_eur: float,
                                    ramp_fuel_per_mw_gj: float,
                                    fuel_price_per_mwh_LHV_eur_getter: Callable[[Any], float],
                                    efficiency_el: float,
                                    emissions_per_mwh_LHV_t: float = 0):
    return {
        'variable_costs_per_mwh_eur_getter': lambda cost:
            get_operation_cost_per_mwh_eur(
                variable_o_m_per_mwh_el_eur=variable_o_m_per_mwh_el_eur,
                fuel_price_per_mwh_LHV_eur=fuel_price_per_mwh_LHV_eur_getter(cost),
                efficiency_el=efficiency_el,
                emissions_per_mwh_LHV_t=emissions_per_mwh_LHV_t,
                emission_price_per_t_eur=cost.emission_price_per_t_eur),
        'co2_t_mwh': emissions_per_mwh_LHV_t / efficiency_el,
        'ramp_up_cost_mw_eur_getter': lambda cost:
            get_ramp_up_cost_per_mw_eur(
                wear_cost_per_mw_eur=wear_cost_per_mw_eur,
                ramp_fuel_per_mw_gj=ramp_fuel_per_mw_gj,
                fuel_cost_per_mwh_LWH=fuel_price_per_mwh_LHV_eur_getter(cost),
                emissions_per_mwh_LHV_t=emissions_per_mwh_LHV_t,
                emission_price_per_t_eur=cost.emission_price_per_t_eur),
    }


def get_operation_cost_per_mwh_eur(variable_o_m_per_mwh_el_eur: float,
                                   fuel_price_per_mwh_LHV_eur: float,
                                   efficiency_el: float,
                                   emissions_per_mwh_LHV_t: float,
                                   emission_price_per_t_eur: float):
    costs_per_mwh_LHV_eur = fuel_price_per_mwh_LHV_eur + \
        emissions_per_mwh_LHV_t * emission_price_per_t_eur
    costs_per_mwh_el_eur = costs_per_mwh_LHV_eur / efficiency_el
    return costs_per_mwh_el_eur + variable_o_m_per_mwh_el_eur


def get_ramp_up_cost_per_mw_eur(wear_cost_per_mw_eur: float,
                                ramp_fuel_per_mw_gj: float,
                                fuel_cost_per_mwh_LWH: float,
                                emissions_per_mwh_LHV_t: float = 0,
                                emission_price_per_t_eur: float = 0) -> float:
    ramp_fuel_per_mw_mwh_LHV = ramp_fuel_per_mw_gj / 3.6
    fuel_costs = ramp_fuel_per_mw_mwh_LHV * fuel_cost_per_mwh_LWH

    emissions_price_per_mwh_LHV_eur = emission_price_per_t_eur * emissions_per_mwh_LHV_t
    emissions_cost = emissions_price_per_mwh_LHV_eur * ramp_fuel_per_mw_mwh_LHV
    return wear_cost_per_mw_eur + fuel_costs + emissions_cost

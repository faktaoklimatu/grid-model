"""
A unified structure for passing around the set of prices of fuels.
"""

from dataclasses import dataclass
from typing import TypedDict, Union


class InputCostsDict(TypedDict):
    emission_price_per_t_eur: float
    lignite_price_per_mwh_LHV_eur: float
    biogas_price_per_mwh_LHV_eur: float
    biomass_price_per_mwh_LHV_eur: float
    biomethane_price_per_mwh_LHV_eur: float
    fossil_gas_price_per_mwh_LHV_eur: float
    hard_coal_price_per_mwh_LHV_eur: float
    heating_oil_price_per_mwh_LHV_eur: float
    solid_waste_per_mwh_LHV_eur: float


@dataclass
class InputCosts:
    emission_price_per_t_eur: float
    """Price of carbon emissions in EUR per metric ton of CO₂"""
    # Prices in EUR per MWh of lower heating value:
    lignite_price_per_mwh_LHV_eur: float
    biogas_price_per_mwh_LHV_eur: float
    biomass_price_per_mwh_LHV_eur: float
    biomethane_price_per_mwh_LHV_eur: float
    fossil_gas_price_per_mwh_LHV_eur: float
    hard_coal_price_per_mwh_LHV_eur: float
    heating_oil_price_per_mwh_LHV_eur: float
    solid_waste_per_mwh_LHV_eur: float


_2028_cost: InputCostsDict = {
    "emission_price_per_t_eur": 90,
    # Average lignite price approximately in line with ERAA 2025 methodology.
    "lignite_price_per_mwh_LHV_eur": 8,
    "biogas_price_per_mwh_LHV_eur": 40,
    "biomass_price_per_mwh_LHV_eur": 39.2,
    # Approximately in line with TYNDP 2024 scenarios methodology which
    # assumes 18.8 €/GJ = 67.68 €/MWh in 2030.
    "biomethane_price_per_mwh_LHV_eur": 68,
    # Based on Dutch TTF futures for 2028 as of early December 2025.
    "fossil_gas_price_per_mwh_LHV_eur": 25,
    # Based on API2 Rotterdam futures for 2028 as of early December 2025.
    # Computed from price per 1000 tons of coal (which is 8.141 MWh of energy).
    "hard_coal_price_per_mwh_LHV_eur": 105 / 8.141,
    # Derived from Low Sulphur Gasoil futures (ICE) for 2028 and beyond as of early
    # December 2025. These are quoted in US$/t, the value below is following FX
    # conversoin to €/t and divided by the typical NCV/LHV (11.8 MWh/t).
    "heating_oil_price_per_mwh_LHV_eur": 522 / 11.8,
    "solid_waste_per_mwh_LHV_eur": 0,
}

_2030_cost: InputCostsDict = _2028_cost | {
    "emission_price_per_t_eur": 96,
    # Based on Dutch TTF futures for 2030 as of early December 2025.
    "fossil_gas_price_per_mwh_LHV_eur": 22,
}

_2033_cost: InputCostsDict = _2030_cost | {
    "emission_price_per_t_eur": 106,
    # Based on Dutch TTF futures for 2033 as of early December 2025.
    "fossil_gas_price_per_mwh_LHV_eur": 23,
}

_input_costs: dict[str, InputCostsDict] = {
    "2028": _2028_cost,
    "2030": _2030_cost,
    "2033": _2033_cost,
}


def get_input_costs(
    input_costs: Union[InputCosts, str, dict[str, float]],
) -> InputCosts:
    if isinstance(input_costs, InputCosts):
        return input_costs

    if isinstance(input_costs, str):
        if input_costs not in _input_costs:
            raise KeyError(f"Input costs key {input_costs} not defined")
        input_costs = _input_costs[input_costs]

    return InputCosts(**input_costs)

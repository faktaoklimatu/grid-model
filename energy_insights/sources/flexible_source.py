"""
Provides structures for flexible power sources in the grid.
"""

import enum
from copy import deepcopy
from dataclasses import dataclass, fields
from typing import Optional, Union

from ..color_map import ColorMap
from ..grid_opex_utils import get_flexible_source_cost_params
from .basic_source import Source, fix_source_params, NUCLEAR_FUEL_PRICE_EUR_MWH_EL
from .economics import SourceEconomics, extract_economics_params, usd_to_eur_2022
from .heat_source import (
    BackPressureTurbine,
    ExtractionTurbine,
    HeatRecoveryUnit,
    HeatSource,
)
from .input_costs import InputCosts, get_input_costs
from .reserves import FastReservesProvider, SlowReservesProvider


@enum.unique
class FlexibleSourceType(enum.StrEnum):
    BIOGAS = "biogas"
    """General biogass/biomethane-fired plant"""
    BIOGAS_PEAK = "bio_peak"
    """Biogass-fired OCGT plant"""
    COAL = "coal"
    """Hard coal-fired power plant"""
    COAL_BACKPRESSURE = "coal_bp"
    """Hard coal-fired power plant with a back-pressure turbine for
    heat co-generation"""
    COAL_EXTRACTION = "coal_ex"
    """Hard coal-fired power plant with a steam extraction turbine for
    heat co-generation"""
    COAL_SUPERCRITICAL = "coal_sc"
    """New, highly efficient hard/bituminous coal-fired power plant"""
    GAS = "gas"
    """General natural gas-fired power plant"""
    GAS_CCGT = "gas_ccgt"
    """Natural gas-fired CCGT power plant"""
    GAS_CCGT_CCS = "gas_ccgt_ccs"
    """Natural gas-fired CCGT power plant with carbon capture"""
    GAS_CHP = "gas_chp"
    """Natural gas-fired CCGT power plant with extraction turbine
    heat co-generation"""
    GAS_ENGINE = "gas_eng"
    """Natural gas-fired combustion engine"""
    GAS_ENGINE_CHP = "gas_eng_chp"
    """Natural gas-fired combustion engine with heat extraction"""
    GAS_PEAK = "gas_peak"
    """Peaking gas-fired OCGT power plant"""
    LIGNITE = "lig"
    """General lignite-fired power plant"""
    LIGNITE_BACKPRESSURE = "lig_bp"
    """Lignite-fired power plant with a back-pressure turbine for heat
    co-generation"""
    LIGNITE_EXTRACTION = "lig_ex"
    """Lignite-fired power plant with a steam extraction turbine for
    heat co-generation"""
    LIGNITE_OLD = "lig_old"
    """Old, inefficient, highly polluting lignite-fired power plant"""
    LIGNITE_SUPERCRITICAL = "lig_sc"
    """New, highly efficient lignite-fired power plant"""
    LOSS_OF_LOAD = "eens"
    """Expected energy not served. Virtual source of power when load is
    higher than production."""
    MAZUT = "mazut"
    """Mazut-fired power plant"""
    FOSSIL_OIL = "oil"
    """Power generation from burning fossil-based fuel oils."""
    OTHER_RES = "o_RES"
    """Abstract 'other renewables' power source. Equivalent to biogas
    for now."""
    SOLID_BIOMASS = "bio"
    """General solid biomass-burning power plant"""
    SOLID_BIOMASS_CHP = "b_CHP"
    """Combined heat and power solid biomass-burning power plant"""
    WASTE = "waste"
    """Municipial solid waste-to-energy (WtE) incinerator"""
    SMR = "smr"
    """Small modular nuclear"""
    DSR = "dsr"
    """Demand reduction when generation is not sufficient (very expensive)"""


class SourceConstraint:
    def __add__(self, other):
        raise TypeError("Incompatible constraints")


@dataclass
class CapacityFactorConstraint(SourceConstraint):
    max_capacity_factor: float
    """Maximum annual-averaged capacity factor between 0 and 1."""

    def __add__(self, other):
        if not isinstance(other, CapacityFactorConstraint):
            raise TypeError("Incompatible constraints")
        if other.max_capacity_factor != self.max_capacity_factor:
            raise ValueError(
                "Incompatible constraints: capacity factors must be identical"
            )
        return deepcopy(self)

    def __post_init__(self):
        if not (0 < self.max_capacity_factor <= 1):
            raise ValueError(
                f"Invalid capacity factor ({self.max_capacity_factor}), must be between 0 and 1"
            )


@dataclass
class ProductionConstraint(SourceConstraint):
    max_total_twh: float
    """Maximum allowed annual production in TWh in terms of electricity
    equivalent (in the case of CHP)."""

    def __add__(self, other):
        if not isinstance(other, ProductionConstraint):
            raise TypeError("Incompatible constraints")
        return ProductionConstraint(self.max_total_twh + other.max_total_twh)

    def __post_init__(self):
        if self.max_total_twh <= 0:
            raise ValueError(
                f"Invalid production constraint ({self.max_total_twh}), must be positive"
            )


@dataclass
class FlexibleSource(Source):
    type: FlexibleSourceType
    ramp_rate: float
    """Power (expressed as ratio of `capacity_mw`) by which the current
    production can change up or down in one hour."""
    ramp_up_cost_mw_eur: float
    """Fixed cost for increasing output by 1 MW."""
    heat: Optional[HeatSource]
    """Type of heat production, if any."""
    constraint: Optional[SourceConstraint]
    """Constraint on capacity factor or total annual production."""

    def __add__(self, other):
        basic_source = Source.__add__(self, other)
        source_dict = {
            field.name: getattr(basic_source, field.name) for field in fields(Source)
        }

        assert (
            self.ramp_rate == other.ramp_rate
        ), f"ramp rates != for {self.type} and {other.type}"
        assert (
            self.ramp_up_cost_mw_eur == other.ramp_up_cost_mw_eur
        ), f"ramp_up_cost_mw_eur != for {self.type} and {other.type}"
        assert self.heat == other.heat, f"heat != for {self.type} and {other.type}"

        # Reconcile production constraints. Matrix of possible cases:
        #   self    other   result
        #   ------- ------- ---------------
        #   None    None    None
        #   any     None    self
        #   None    any     other
        #   cap     cap     check cap is same
        #   prod    prod    sum
        #   anything else   error
        if self.constraint is None:
            constraint = other.constraint
        elif other.constraint is None:
            constraint = self.constraint
        else:
            # This may raise an exception. Let it propagate.
            constraint = self.constraint + other.constraint

        return FlexibleSource(
            **source_dict,
            ramp_rate=self.ramp_rate,
            ramp_up_cost_mw_eur=self.ramp_up_cost_mw_eur,
            heat=self.heat,
            constraint=constraint,
        )


# Efficiency constants
__efficiency_biogas = 0.45
__efficiency_biomass_chp = 0.27
__efficiency_ccgt = 0.56
__efficiency_ccgt_ccs = 0.51
# Central estimate for 2020 from Danish Energy Agency
# https://ens.dk/en/our-services/projections-and-models/technology-data/technology-data-generation-electricity-and
__efficiency_ocgt = 0.4
__efficiency_gas_engine = 0.45
__efficiency_coal = 0.4
# Very low electrical efficiency as most of the energy goes to heat.
__efficiency_coal_bp = 0.2
__efficiency_coal_old = 0.36
# Approximately based on the advertised efficiency of the Ledvice
# and Lippendorf lignite-fired supercritical power plants.
# https://www.svetenergie.cz/cz/energetika-zblizka/uhelne-elektrarny/uhelna-elektrarna-podrobne/charakteristika-zdroje/parametry
# https://www.ujv.cz/cs/reference/komplexni-modernizace-elektrarny-prunerov-ii-ceska-republika-2-10359
# https://www.power-technology.com/projects/lippendorf/
__efficiency_coal_supercritical = 0.43
__efficiency_waste = 0.21

# Irrelevant at the moment as fuel price is fixed for MWh_el (the efficiency assumes some
# IV-gen improvements).
__efficiency_nuclear_smr = 0.4


def _get_coal_cost_params(fuel_price_getter, efficiency_el: float, emissions: float):
    return get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=4,
        wear_cost_per_mw_eur=50,
        ramp_fuel_per_mw_gj=18,
        fuel_price_per_mwh_LHV_eur_getter=fuel_price_getter,
        efficiency_el=efficiency_el,
        emissions_per_mwh_LHV_t=emissions,
    )


# Emission factors
__emissions_gas_per_MWh_LHV_t = 0.22
__emissions_gas_ccs_per_MWh_LHV_t = 0.15 * __emissions_gas_per_MWh_LHV_t  # 85% CCS
__emissions_hard_coal_per_MWh_LHV_t = 0.846 * __efficiency_coal
__emissions_heating_oil_per_MWh_LHV_t = 0.27
__emissions_lignite_per_MWh_LHV_t = 1.0 * __efficiency_coal
# Waste incineration does not fall under EU ETS at the moment.
# TODO: In 2030, they will be covered by ETS 1.
__emissions_waste_per_MWh_LHV_t = 0

__coal = {
    "color": ColorMap.COAL,
    "construction_time_years": 4,
    "lifetime_years": 40,
    "fixed_o_m_costs_per_kw_eur": 47,
    "capacity_mw": 0,
    "min_capacity_mw": 0,
}

__lignite = (
    __coal
    | {
        "type": FlexibleSourceType.LIGNITE,
        "ramp_rate": 0.1,
        "overnight_costs_per_kw_eur": 3000,
        "reserves": SlowReservesProvider(min_dispatch_fraction=0.5),
    }
    | _get_coal_cost_params(
        lambda cost: cost.lignite_price_per_mwh_LHV_eur,
        __efficiency_coal,
        __emissions_lignite_per_MWh_LHV_t,
    )
)

__lignite_old = (
    __lignite
    | {"type": FlexibleSourceType.LIGNITE_OLD}
    | _get_coal_cost_params(
        lambda cost: cost.lignite_price_per_mwh_LHV_eur,
        __efficiency_coal_old,
        __emissions_lignite_per_MWh_LHV_t,
    )
)

__lignite_supercritical = (
    __lignite
    | {"type": FlexibleSourceType.LIGNITE_SUPERCRITICAL}
    | _get_coal_cost_params(
        lambda cost: cost.lignite_price_per_mwh_LHV_eur,
        __efficiency_coal_supercritical,
        __emissions_lignite_per_MWh_LHV_t,
    )
)

__lignite_extraction = __lignite | {
    "type": FlexibleSourceType.LIGNITE_EXTRACTION,
    "heat": ExtractionTurbine(
        base_ratio_heat_mw_per_el_mw=0,
        # Allow for higher heat extraction for maximum total
        # efficiency of 87%.
        heat_mw_per_decreased_el_mw=2.8,
        min_ratio_el=0.4,
    ),
    "reserves": None,
}

__lignite_back_pressure = (
    __lignite
    | {
        "type": FlexibleSourceType.LIGNITE_BACKPRESSURE,
        "heat": BackPressureTurbine.canonical(),
        "reserves": None,
    }
    | _get_coal_cost_params(
        lambda cost: cost.lignite_price_per_mwh_LHV_eur,
        __efficiency_coal_bp,
        __emissions_lignite_per_MWh_LHV_t,
    )
)

__hard_coal = (
    __coal
    | {
        "type": FlexibleSourceType.COAL,
        "ramp_rate": 0.15,
        # IEA's World Energy Outlook 2023 for Europe (estimates stay constant in time and per scenario).
        # https://iea.blob.core.windows.net/assets/2b0ded44-6a47-495b-96d9-2fac0ac735a8/WorldEnergyOutlook2023.pdf
        "overnight_costs_per_kw_eur": usd_to_eur_2022(2000),
        "reserves": SlowReservesProvider(min_dispatch_fraction=0.45),
    }
    | _get_coal_cost_params(
        lambda cost: cost.hard_coal_price_per_mwh_LHV_eur,
        __efficiency_coal,
        __emissions_hard_coal_per_MWh_LHV_t,
    )
)

__hard_coal_extraction = __hard_coal | {
    "type": FlexibleSourceType.COAL_EXTRACTION,
    "heat": ExtractionTurbine(
        base_ratio_heat_mw_per_el_mw=0,
        # Allow for higher heat extraction for maximum total
        # efficiency of 87%.
        heat_mw_per_decreased_el_mw=2.8,
        min_ratio_el=0.4,
    ),
    "reserves": None,
}

__hard_coal_back_pressure = (
    __hard_coal
    | {
        "type": FlexibleSourceType.COAL_BACKPRESSURE,
        "heat": BackPressureTurbine.canonical(),
        "reserves": None,
    }
    | _get_coal_cost_params(
        lambda cost: cost.hard_coal_price_per_mwh_LHV_eur,
        __efficiency_coal_bp,
        __emissions_hard_coal_per_MWh_LHV_t,
    )
)

__hard_coal_supercritical = (
    __hard_coal
    | {
        "type": FlexibleSourceType.COAL_SUPERCRITICAL,
    }
    | _get_coal_cost_params(
        lambda cost: cost.hard_coal_price_per_mwh_LHV_eur,
        __efficiency_coal_supercritical,
        __emissions_hard_coal_per_MWh_LHV_t,
    )
)

__waste = {
    "type": FlexibleSourceType.WASTE,
    "color": ColorMap.WASTE,
    "construction_time_years": 3,
    "lifetime_years": 25,
    "fixed_o_m_costs_per_kw_eur": 277,
    "overnight_costs_per_kw_eur": 11773,
    "uptime_ratio": 0.5,
    "ramp_rate": 0.25,
    "discount_rate": 1.05,
    "capacity_mw": 0,
    "min_capacity_mw": 0,
} | get_flexible_source_cost_params(
    variable_o_m_per_mwh_el_eur=38.5,
    wear_cost_per_mw_eur=50,
    ramp_fuel_per_mw_gj=18,
    fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.solid_waste_per_mwh_LHV_eur,
    efficiency_el=__efficiency_waste,
    emissions_per_mwh_LHV_t=__emissions_waste_per_MWh_LHV_t,
)

# For simplicity as this is quite rare.
__mazut = __hard_coal | {
    "type": FlexibleSourceType.MAZUT,
}

__gas = {
    "type": FlexibleSourceType.GAS,
    "color": ColorMap.GAS,
    "ramp_rate": 0.5,
    "capacity_mw": 0,
    "min_capacity_mw": 0,
    "discount_rate": 1.10,
}

__gas_ccgt = (
    __gas
    | {
        "type": FlexibleSourceType.GAS_CCGT,
        "construction_time_years": 3,
        "lifetime_years": 30,
        "fixed_o_m_costs_per_kw_eur": 15,
        # IEA World Energy Outlook 2024, Stated Policies Scenario, page 333,
        # average of EU costs in 2023 and 2030.
        # https://iea.blob.core.windows.net/assets/140a0470-5b90-4922-a0e9-838b3ac6918c/WorldEnergyOutlook2024.pdf#page=333
        "overnight_costs_per_kw_eur": 924,
        "reserves": FastReservesProvider(min_dispatch_fraction=0.2),
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=4,
        wear_cost_per_mw_eur=25,
        ramp_fuel_per_mw_gj=7.6,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.fossil_gas_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_ccgt,
        emissions_per_mwh_LHV_t=__emissions_gas_per_MWh_LHV_t,
    )
)

__gas_chp = (
    __gas_ccgt
    | {
        "type": FlexibleSourceType.GAS_CHP,
        # Central estimates for 2030 from the Danish Energy Agency,
        # February 2025 edition, source type "Gas turbine,
        # combined cycle - extraction - natural gas - large".
        "overnight_costs_per_kw_eur": 1204,
        "fixed_o_m_costs_per_kw_eur": 40.4,
        "heat": ExtractionTurbine(
            base_ratio_heat_mw_per_el_mw=0,
            # Allow for higher heat extraction for maximum total efficiency
            # of almost 90%.
            heat_mw_per_decreased_el_mw=2,
            # Prefer electricity production and prevent higher than 100%
            # total efficiency.
            min_ratio_el=0.4,
        ),
        "reserves": None,
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=6.1,
        wear_cost_per_mw_eur=25,
        ramp_fuel_per_mw_gj=7.6,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.fossil_gas_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_ccgt,
        emissions_per_mwh_LHV_t=__emissions_gas_per_MWh_LHV_t,
    )
)

__ocgt = {
    "ramp_rate": 0.5,
    "construction_time_years": 1,
    "lifetime_years": 25,
    "fixed_o_m_costs_per_kw_eur": 11,
    # Central estimate for 2030 from Danish Energy Agency,
    # February 2025 edition, source type "OCGT - Natural gas".
    # https://ens.dk/en/our-services/projections-and-models/technology-data/technology-data-generation-electricity-and
    "overnight_costs_per_kw_eur": 642,
    "capacity_mw": 0,
    "min_capacity_mw": 0,
}

__gas_ocgt = (
    __ocgt
    | __gas
    | {
        "type": FlexibleSourceType.GAS_PEAK,
        "reserves": FastReservesProvider(min_dispatch_fraction=0.0),
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=7,
        wear_cost_per_mw_eur=20,
        ramp_fuel_per_mw_gj=0.2,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.fossil_gas_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_ocgt,
        emissions_per_mwh_LHV_t=__emissions_gas_per_MWh_LHV_t,
    )
)

__gas_engine = (
    __gas_ocgt
    | {
        "type": FlexibleSourceType.GAS_ENGINE,
        "ramp_rate": 1.0,
        "fixed_o_m_costs_per_kw_eur": 9.1,
        "overnight_costs_per_kw_eur": 683,
        "discount_rate": 1.07,
        "reserves": FastReservesProvider(min_dispatch_fraction=0.3),
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=8.7,
        wear_cost_per_mw_eur=20,
        ramp_fuel_per_mw_gj=0.2,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.fossil_gas_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_gas_engine,
        emissions_per_mwh_LHV_t=__emissions_gas_per_MWh_LHV_t,
    )
)

__gas_engine_chp = __gas_engine | {
    "type": FlexibleSourceType.GAS_ENGINE_CHP,
    "heat": HeatRecoveryUnit.canonical(),
    "reserves": None,
}

__gas_ccgt_ccs = (
    __gas_ccgt
    | {
        "type": FlexibleSourceType.GAS_CCGT_CCS,
        "color": ColorMap.GAS_WITH_CCS,
        "fixed_o_m_costs_per_kw_eur": 40,
        # Mid of the range of Lazard's 2023 Levelized Cost Of Energy+:
        # https://www.lazard.com/research-insights/2023-levelized-cost-of-energyplus/
        "overnight_costs_per_kw_eur": usd_to_eur_2022(2300),
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=10,
        wear_cost_per_mw_eur=43,
        ramp_fuel_per_mw_gj=7.6,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.fossil_gas_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_ccgt_ccs,
        emissions_per_mwh_LHV_t=__emissions_gas_ccs_per_MWh_LHV_t,
    )
)

# Burning of light heating oil in a single-cycle turbine.
__fossil_oil = (
    __gas_ocgt
    | {
        "type": FlexibleSourceType.FOSSIL_OIL,
        "color": ColorMap.GAS_PEAKERS,
        "reserves": FastReservesProvider(min_dispatch_fraction=0.3),
    }
    | get_flexible_source_cost_params(
        # Maintenance costs similar to OCGT.
        variable_o_m_per_mwh_el_eur=4,
        wear_cost_per_mw_eur=20,
        ramp_fuel_per_mw_gj=0.2,
        # Heating oil-specific costs.
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.heating_oil_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_ocgt,
        emissions_per_mwh_LHV_t=__emissions_heating_oil_per_MWh_LHV_t,
    )
)

__biomass = {
    "renewable": True,
    "color": ColorMap.BIOMASS,
    "capacity_mw": 0,
    "min_capacity_mw": 0,
    "discount_rate": 1.05,
}

__solid_biomass = (
    __biomass
    | {  # Biomass burning/co-burning
        "type": FlexibleSourceType.SOLID_BIOMASS,
        "ramp_rate": 0.15,
        "construction_time_years": 5,
        "lifetime_years": 25,
        "fixed_o_m_costs_per_kw_eur": 40,
        "overnight_costs_per_kw_eur": 2500,
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=10,
        wear_cost_per_mw_eur=50,
        ramp_fuel_per_mw_gj=18,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.biomass_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_coal,
    )
)

__solid_biomass_chp = (
    __solid_biomass
    | {  # Biomass burning/co-burning CHP.
        "type": FlexibleSourceType.SOLID_BIOMASS_CHP,
        "fixed_o_m_costs_per_kw_eur": 139,
        "overnight_costs_per_kw_eur": 4860,
        "heat": ExtractionTurbine.canonical(),
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=6.6,
        wear_cost_per_mw_eur=50,
        ramp_fuel_per_mw_gj=18,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.biomass_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_biomass_chp,
    )
)

# Biogas burning.
__biogas = (
    __biomass
    | {
        "type": FlexibleSourceType.BIOGAS,
        "ramp_rate": 0.5,
        "construction_time_years": 1,
        "lifetime_years": 25,
        "fixed_o_m_costs_per_kw_eur": 9,
        "overnight_costs_per_kw_eur": 683,
        "reserves": FastReservesProvider(min_dispatch_fraction=0.4),
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=8.7,
        wear_cost_per_mw_eur=20,
        ramp_fuel_per_mw_gj=0.2,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.biogas_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_biogas,
    )
)

__biomethane_ocgt = (
    __biomass
    | __ocgt
    | {
        "type": FlexibleSourceType.BIOGAS_PEAK,
        "color": ColorMap.BIOMASS_PEAKERS,
        "reserves": FastReservesProvider(min_dispatch_fraction=0.0),
    }
    | get_flexible_source_cost_params(
        variable_o_m_per_mwh_el_eur=4,
        wear_cost_per_mw_eur=20,
        ramp_fuel_per_mw_gj=0.2,
        fuel_price_per_mwh_LHV_eur_getter=lambda cost: cost.biomethane_price_per_mwh_LHV_eur,
        efficiency_el=__efficiency_ocgt,
    )
)

__smr = {
    "type": FlexibleSourceType.SMR,
    "color": ColorMap.SMR,
    "capacity_mw": 0,
    "min_capacity_mw": 0,
    # Roughly based on https://www.researchgate.net/publication/337548100_ANS_2019_Winter_Meeting_Presentation_Assessment_of_Small_Modular_Reactors_SMRs_for_Load-Following_Capabilities.
    "ramp_rate": 0.5,
    # Based on https://www.mpo.cz/assets/en/guidepost/for-the-media/press-releases/2023/11/Czech-SMR-Roadmap_EN.pdf.
    "lifetime_years": 60,
    # Based on https://www.eia.gov/outlooks/aeo/assumptions/pdf/elec_cost_perf.pdf, but assuming
    # technological optimism factor of 1.4, instead.
    "construction_time_years": 6,
    "overnight_costs_per_kw_eur": usd_to_eur_2022(10626),
    "fixed_o_m_costs_per_kw_eur": 100,
} | get_flexible_source_cost_params(
    variable_o_m_per_mwh_el_eur=4,
    # Based on PEMMDB - standard nuclear.
    wear_cost_per_mw_eur=21,
    ramp_fuel_per_mw_gj=8,
    fuel_price_per_mwh_LHV_eur_getter=lambda cost: NUCLEAR_FUEL_PRICE_EUR_MWH_EL
    * __efficiency_nuclear_smr,
    efficiency_el=__efficiency_nuclear_smr,
)

__dsr = {
    "type": FlexibleSourceType.DSR,
    "variable_costs_per_mwh_eur": 2_000,
    "color": ColorMap.DSR,
    # Don't let DSR provide reserves for now.
    # "reserves": SlowReservesProvider(min_dispatch=0.0),
}

__loss_of_load = {
    "type": FlexibleSourceType.LOSS_OF_LOAD,
    "capacity_mw": 1_000_000,  # artificial to cover extra load
    "min_capacity_mw": 1_000_000,  # no need to optimize capex (there are anyway no costs).
    "variable_costs_per_mwh_eur": 4_000,  # Reflects value of lost load from MAF CZ 2022.
    "color": ColorMap.LOSS_OF_LOAD,
    "virtual": True,
    # Allow EENS/LOLE to produce heat as well.
    "heat": ExtractionTurbine(
        base_ratio_heat_mw_per_el_mw=0,
        # Doesn't matter for thise use case.
        heat_mw_per_decreased_el_mw=1,
        # Allow "producing" heat shortage without necessarily inducing
        # power shortage.
        min_ratio_el=0,
    ),
}

flexible_source_defaults: dict[FlexibleSourceType, dict] = {
    FlexibleSourceType.BIOGAS: __biogas,
    FlexibleSourceType.BIOGAS_PEAK: __biomethane_ocgt,
    FlexibleSourceType.COAL: __hard_coal,
    FlexibleSourceType.COAL_BACKPRESSURE: __hard_coal_back_pressure,
    FlexibleSourceType.COAL_EXTRACTION: __hard_coal_extraction,
    FlexibleSourceType.COAL_SUPERCRITICAL: __hard_coal_supercritical,
    FlexibleSourceType.DSR: __dsr,
    FlexibleSourceType.FOSSIL_OIL: __fossil_oil,
    FlexibleSourceType.GAS: __gas,
    FlexibleSourceType.GAS_CCGT: __gas_ccgt,
    FlexibleSourceType.GAS_CCGT_CCS: __gas_ccgt_ccs,
    FlexibleSourceType.GAS_CHP: __gas_chp,
    FlexibleSourceType.GAS_ENGINE: __gas_engine,
    FlexibleSourceType.GAS_ENGINE_CHP: __gas_engine_chp,
    FlexibleSourceType.GAS_PEAK: __gas_ocgt,
    FlexibleSourceType.LIGNITE: __lignite,
    FlexibleSourceType.LIGNITE_BACKPRESSURE: __lignite_back_pressure,
    FlexibleSourceType.LIGNITE_EXTRACTION: __lignite_extraction,
    FlexibleSourceType.LIGNITE_OLD: __lignite_old,
    FlexibleSourceType.LIGNITE_SUPERCRITICAL: __lignite_supercritical,
    FlexibleSourceType.LOSS_OF_LOAD: __loss_of_load,
    FlexibleSourceType.MAZUT: __mazut,
    FlexibleSourceType.OTHER_RES: __biogas | {"type": FlexibleSourceType.OTHER_RES},
    FlexibleSourceType.SMR: __smr,
    FlexibleSourceType.SOLID_BIOMASS: __solid_biomass,
    FlexibleSourceType.SOLID_BIOMASS_CHP: __solid_biomass_chp,
    FlexibleSourceType.WASTE: __waste,
}

_flexible_sources: dict[str, dict[FlexibleSourceType, dict]] = {}


def _fix_flexible_source_params(flexible_source: dict, costs: InputCosts):
    # Define variable costs based on cost input.
    if "variable_costs_per_mwh_eur_getter" in flexible_source:
        cost_getter = flexible_source.pop("variable_costs_per_mwh_eur_getter")
        flexible_source["variable_costs_per_mwh_eur"] = cost_getter(costs)

    if subsidy_eur_per_mwh := flexible_source.pop("subsidy_eur_per_mwh", None):
        flexible_source["variable_costs_per_mwh_eur"] -= subsidy_eur_per_mwh

    if "ramp_up_cost_mw_eur_getter" in flexible_source:
        cost_getter = flexible_source.pop("ramp_up_cost_mw_eur_getter")
        flexible_source["ramp_up_cost_mw_eur"] = cost_getter(costs)

    flexible_source = fix_source_params(flexible_source)

    # Set trivial default values.
    flexible_source.setdefault("ramp_rate", 1.0)
    flexible_source.setdefault("ramp_up_cost_mw_eur", 0)
    assert (
        0 < flexible_source["ramp_rate"] <= 1
    ), "ramp_rate must be in the interval (0, 1]"
    flexible_source.setdefault("heat", None)
    flexible_source.setdefault("constraint", None)

    uptime_ratio = flexible_source.pop("uptime_ratio", None)
    max_total_twh = flexible_source.pop("max_total_twh", None)
    if uptime_ratio and max_total_twh:
        raise ValueError(
            "Cannot specify both uptime_ratio and max_total_twh at the same time"
        )
    if uptime_ratio:
        flexible_source["constraint"] = CapacityFactorConstraint(uptime_ratio)
    elif max_total_twh:
        flexible_source["constraint"] = ProductionConstraint(max_total_twh)

    return flexible_source


def get_flexible_sources(
    flexible_sources: Union[str, dict[FlexibleSourceType, dict]],
    input_costs: Union[str, dict[str, float]],
) -> dict[FlexibleSourceType, FlexibleSource]:
    cost: InputCosts = get_input_costs(input_costs)
    if isinstance(flexible_sources, str):
        sources_dict = deepcopy(_flexible_sources[flexible_sources])
    else:
        sources_dict = deepcopy(flexible_sources)

    # Make sure there is always the fallback to loss of lod. The default
    # parameters are be loaded later down.
    if FlexibleSourceType.LOSS_OF_LOAD not in sources_dict:
        sources_dict[FlexibleSourceType.LOSS_OF_LOAD] = {}

    def create_source(key: FlexibleSourceType, params_add: dict) -> FlexibleSource:
        source_dict = _fix_flexible_source_params(
            flexible_source_defaults[key] | params_add, cost
        )
        economics = SourceEconomics(**extract_economics_params(source_dict))
        return FlexibleSource(economics=economics, **source_dict)

    return {
        key: create_source(key, params_add) for key, params_add in sources_dict.items()
    }

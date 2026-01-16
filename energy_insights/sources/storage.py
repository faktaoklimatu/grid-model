"""
Provides structures for grid storage facilities.
"""

import enum
from copy import deepcopy
from dataclasses import dataclass, fields
from typing import Optional, Union

from numpy import average

from ..color_map import ColorMap
from ..data_keys import Keys
from ..logging import get_logger
from .basic_source import Source, fix_source_params
from .economics import SourceEconomics, extract_economics_params
from .reserves import FastReservesProvider

logger = get_logger(__name__)


@enum.unique
class StorageUse(enum.Enum):
    ELECTRICITY = 1
    """Standard storage for electricity, e.g. pumped hydro, batteries,
    V2G, etc."""
    ELECTRICITY_AS_BASIC = 2
    """Storage for electricity that pretends to be a basic source (in
    plots)."""
    DEMAND_FLEXIBILITY = 3
    """Whether this models demand flexibility and should only alter the
    plotted demand curve."""
    HEAT = 4
    """Storage for heat (in district heating systems)."""
    POWER_TO_HEAT = 5
    """Storage/transformation of electricity to heat, e.g. using heat
    pumps or electric boilers. Charging takes electricty off the grid
    transforming it into heat directly. Discharging (heat-to-power) is
    currently not supported."""

    def is_electricity(self) -> bool:
        """Check if the storage is used purely for electricity."""
        return self == StorageUse.ELECTRICITY or self == StorageUse.ELECTRICITY_AS_BASIC


@enum.unique
class StorageType(enum.StrEnum):
    DSR = "dsr"
    """Demand-side response."""
    ELECTRIC_BOILER = "eboil"
    """Electric boiler."""
    HYDRO_FLEX = "hydro_flex"
    """Hydro flexibility."""
    HEAT = "heat"
    """General heat storage."""
    HEAT_DISTRIBUTION = "heat_dist"
    """Some sort of flexibility/storage in the district heating pipes."""
    HEAT_FLEX = "hp_flex"
    """Flexibility of heat pump electricity demand (both heating and cooling)."""
    HEAT_PUMP = "hp"
    """Heat pump."""
    HOT_WATER_TANK = "hot"
    """Large hot-water tank for heat storage in district heating system."""
    HYDROGEN = "h2"
    """Hydrogen-based storage."""
    HYDROGEN_PEAK = "h2p"
    """Hydrogen-based storage with OCGT turbines."""
    LI = "li"
    """Generic lithium-ion batteries."""
    LI_2H = "li2"
    """2-hour lithium-ion batteries."""
    LI_4H = "li4"
    """4-hour lithium-ion batteries."""
    LOAD_SHIFT_3H = "ls3h"
    """Shifting of load within 3-hour windows."""
    LOAD_SHIFT_12H = "ls12h"
    """Shifting of load within 12-hour windows."""
    VEHICLE_TO_GRID_50KWH_11KW = "v2g11"
    """Vehicle to grid with 50 kWh batteries and 11 kW slow charging."""
    VEHICLE_TO_GRID_50KWH_3KW = "v2g3"
    """Vehicle to grid with 50 kWh batteries and 3 kW slow charging."""
    VEHICLE_TO_GRID = "v2g"
    """Generic vehicle-to-grid storage/flexibility."""
    SMART_CHARGING = "ecars"
    """Generic smart charging of electric vehicles -- load shifting of
    charging power."""
    PONDAGE = "h_pond"
    """Pondage hydro power, typically a turbine on a river with a small
    reservoir upstream for short-term storage. Lies conceptually between
    a reservoir and run-of-river hydro."""
    PUMPED = "pump"
    """Pumped hydro power, closed-loop (can only be charged by drawing power)."""
    PUMPED_OPEN = "pump_open"
    """Pumped hydro power, open-loop (allows for river inflows)."""
    RESERVOIR = "h_dams"
    """Reservoir hydro power, typically a large reservoir with a turbine
    for flexible power output."""
    ROR = "h_ror"
    """Run-of-river hydro power, typically a smaller turbine with no
    storage capacity and little flexibility."""


@dataclass
class Storage(Source):
    type: StorageType
    # Use for this device.
    use: StorageUse
    capacity_mw_charging: float
    min_capacity_mw_charging: float
    paid_off_capacity_mw_charging: float
    """Charging capacity that is considered already paid off. Must be
    lower or equal to the minimal charging capacity of this storage.
    This means that paid off capacity does not influence optimization,
    it only decreases total system costs (for this storage and overall)."""
    min_charging_capacity_ratio_to_VRE: float
    """Capacity for charging is enforced to at least this ratio of thea
    sum of capacity of solar, onshore, offshore. Must be non-negative,
    often will be a couple of percent (such as 0.1)."""
    # Not enforced in the LP, only used for statistics.
    separate_charging: Optional[SourceEconomics]

    # If the storage has separate charging, these bounds are multiplied by number of weather years
    # so that yearly required outflow or allowed inflow of storage (such as on hydrogen market),
    # captured by `final_energy_mwh` or `min_final_energy_mwh` get scaled to number of years.
    # If the storage has not separate charging, all these bounds depend on capacity (get decreased
    # with capex optimization).
    # TODO: This distinction is a bit arbitrary, maybe make it somehow clearer?
    max_energy_mwh: float
    initial_energy_mwh: float
    final_energy_mwh: float
    """The ideal final energy. Ending up with more results in financial
    gains, ending up with less (if allowed by `min_final_energy_mwh`)
    results in further costs."""
    min_final_energy_mwh: float
    """The strict lower limit for final energy of the storage."""
    cycle_length_hours: Optional[int]
    """If specified, the state of charge of this storage must be equal
    every `cycle_length_hours` hours. This is checked at the beginning
    of each period. The cycle should ideally divide the 8760 hours of
    the year evenly."""

    charging_efficiency: float
    discharging_efficiency: float
    loss_rate_per_day: float
    """Loss of state of charge per day (as a ratio of current charge)."""
    use_mwh_per_day: float
    """Constant use of charge (useful for e-mobility). Depends on
    capacity (gets decreased with capex optimization)."""
    cost_sell_buy_mwh_eur: float
    """Bonus in optimization for every MWh of extra energy above
    `final_energy_mwh` or malus for every MWh of energy missing to
    `final_energy_mwh` (if allowed by `min_final_energy_mwh`)."""
    ramp_rate: float
    """Power (expressed as ratio of `capacity_mw + capacity_mw_charging`)
    by which the current (charging - discharging) can change up or down
    in one hour."""
    inflow_hourly_data_key: Optional[str]
    """Optional inflow into the storage (independent of charging)
    specified as a string key of hourly inflow data (in MW)."""
    inflow_min_discharge_ratio: Optional[float]
    """Minimal ratio of inflow that must be directly discharged in the
    given hour. Only has effect if `inflow_hourly_data_key` is
    specified."""
    max_capacity_mw_hourly_data_key: Optional[str]
    """Optional additional discharging capacity limit, specific for each
    modeled hour (specified as a string key of the hourly data, in MW).
    Does not depend on capacity (i.e. does not get decreased with capex
    optimization)."""
    max_capacity_charging_mw_hourly_data_key: Optional[str]
    """Optional additional charging capacity limit for each hour."""
    max_capacity_mw_factor: Optional[float]
    """A factor which hourly data from `max_capacity_mw_hourly_data_key`
    and `max_capacity_charging_mw_hourly_data_key` is multiplied by."""

    def __add__(self, other: "Storage"):
        basic_source = Source.__add__(self, other)
        source_dict = {
            field.name: getattr(basic_source, field.name) for field in fields(Source)
        }

        assert self.use == other.use
        assert self.cycle_length_hours == other.cycle_length_hours
        assert (
            self.separate_charging == other.separate_charging
        ), "charging cost profiles must be same"
        assert self.loss_rate_per_day == other.loss_rate_per_day
        assert self.ramp_rate == other.ramp_rate, f"ramp rates differ for {self.type}"
        assert (
            self.inflow_hourly_data_key == other.inflow_hourly_data_key
        ), "inflows must be same"
        assert self.inflow_min_discharge_ratio == other.inflow_min_discharge_ratio
        assert (
            self.max_capacity_mw_hourly_data_key
            == other.max_capacity_mw_hourly_data_key
        )
        assert (
            self.max_capacity_charging_mw_hourly_data_key
            == other.max_capacity_charging_mw_hourly_data_key
        )
        assert self.max_capacity_mw_factor == other.max_capacity_mw_factor

        # TODO: Consider reverting this to an assert after nuclear study is completed.
        if self.cost_sell_buy_mwh_eur != other.cost_sell_buy_mwh_eur:
            logger.warning(
                f"different `cost_sell_buy_mwh_eur` values for {self.type}, picking"
                "(randomly) one of the values, summary graphs will be wrong"
            )

        if (
            self.min_charging_capacity_ratio_to_VRE
            != other.min_charging_capacity_ratio_to_VRE
        ):
            logger.warning(
                f"different `min_charging_capacity_ratio_to_VRE` values for {self.type}, picking"
                "(randomly) one of the values as this cannot get aggregated correctly"
            )

        # Prevent division by zero in case both sides have zero capacity.
        if self.capacity_mw_charging > 0 or other.capacity_mw_charging > 0:
            charging_efficiency = average(
                [self.charging_efficiency, other.charging_efficiency],
                weights=[self.capacity_mw_charging, other.capacity_mw_charging],
            )
        else:
            assert (
                self.capacity_mw_charging == 0 and other.capacity_mw_charging == 0
            ), f"storage charging capacities must both be zero for {self.type}"
            charging_efficiency = self.charging_efficiency

        if self.capacity_mw > 0 or other.capacity_mw > 0:
            discharging_efficiency = average(
                [self.discharging_efficiency, other.discharging_efficiency],
                weights=[self.capacity_mw, other.capacity_mw],
            )
        else:
            assert (
                self.capacity_mw == 0 and other.capacity_mw == 0
            ), f"storage discharging capacities must both be zero for {self.type}"
            discharging_efficiency = self.discharging_efficiency

        return Storage(
            **source_dict,
            use=self.use,
            capacity_mw_charging=self.capacity_mw_charging + other.capacity_mw_charging,
            min_capacity_mw_charging=self.min_capacity_mw_charging
            + other.min_capacity_mw_charging,
            paid_off_capacity_mw_charging=self.paid_off_capacity_mw_charging
            + other.paid_off_capacity_mw_charging,
            min_charging_capacity_ratio_to_VRE=self.min_charging_capacity_ratio_to_VRE,
            separate_charging=self.separate_charging,
            max_energy_mwh=self.max_energy_mwh + other.max_energy_mwh,
            initial_energy_mwh=self.initial_energy_mwh + other.initial_energy_mwh,
            final_energy_mwh=self.final_energy_mwh + other.final_energy_mwh,
            min_final_energy_mwh=self.min_final_energy_mwh + other.min_final_energy_mwh,
            cycle_length_hours=(
                self.cycle_length_hours + other.cycle_length_hours
                if self.cycle_length_hours is not None
                else None
            ),
            charging_efficiency=charging_efficiency,
            discharging_efficiency=discharging_efficiency,
            loss_rate_per_day=self.loss_rate_per_day,
            use_mwh_per_day=self.use_mwh_per_day + other.use_mwh_per_day,
            cost_sell_buy_mwh_eur=self.cost_sell_buy_mwh_eur,
            ramp_rate=self.ramp_rate,
            inflow_hourly_data_key=self.inflow_hourly_data_key,
            inflow_min_discharge_ratio=self.inflow_min_discharge_ratio,
            max_capacity_mw_hourly_data_key=self.max_capacity_mw_hourly_data_key,
            max_capacity_charging_mw_hourly_data_key=self.max_capacity_charging_mw_hourly_data_key,
            max_capacity_mw_factor=self.max_capacity_mw_factor,
        )


_electric_boiler_as_storage = {
    "type": StorageType.ELECTRIC_BOILER,
    # Consumes electricity, produces heat.
    "use": StorageUse.POWER_TO_HEAT,
    "color": ColorMap.BOILERS,
    # No capacity for discharging -- only heat is allowed to be "stored".
    "capacity_mw": 0,
    "min_capacity_mw": 0,
    # Resistance or electrode boilers typically achieve near 100% efficiency.
    "charging_efficiency": 0.996,
    # Arbitrary -- discharging is neved used. Should not be zero just
    # to be extra careful not to introduce division by zero anywhere.
    "discharging_efficiency": 1,
    # Costs and other economic parameters taken from Danish Energy
    # Agency data sheets, version 15, April 2024. Assuming a mid-sized
    # boiler (400/690 V, up to 5 MW) in 2030.
    "construction_time_years": 1,
    "lifetime_years": 20,
    "fixed_o_m_costs_per_kw_eur": 1.39,
    "overnight_costs_per_kw_eur": 140,
    # Variable O&M only; electricity consumption is endogenous.
    "variable_costs_per_mwh_eur": 0.72,
    # No heat storage allowed, the device is only used to transform
    # electricity into heat.
    "max_energy_mwh": 0,
}
"""Large electric boiler for district heating, technically implemented
as a one-way electricity to heat storage."""

_electrolysis = {
    "construction_time_years": 1,
    "lifetime_years": 25,
    "fixed_o_m_costs_per_kw_eur": 39,
    "overnight_costs_per_kw_eur": 973,
    # No variable O&M, price of input electricity is counted elsewhere.
    "variable_costs_per_mwh_eur": 0,
    # Be careful to use this as it drastically changes optimization
    # -- moving most costs from capex to opex and thus becomes hesitant
    # to use those batteries.
    # "lifetime_hours": 50_000,
}

# Hydrogen storage with hydrogen burning in CCGT plants.
_grid_hydrogen_storage = {
    "type": StorageType.HYDROGEN,
    "charging_efficiency": 0.74,
    "discharging_efficiency": 0.56,
    "color": ColorMap.HYDROGEN,
    # Cost profile of discharging (= H2 burning in a H2-ready CCGT plant).
    "construction_time_years": 1,
    "lifetime_years": 25,
    "fixed_o_m_costs_per_kw_eur": 39,
    "overnight_costs_per_kw_eur": 973,
    "variable_costs_per_mwh_eur": 0,
    # Cost profile for charging (=independent devices for electrolysis)
    "separate_charging": _electrolysis,
    # Make de-facto unbounded storage capacity (to have enough H2 for
    # the start of the year).
    "max_energy_mwh": 200_000_000,
    "initial_energy_mwh": 100_000_000,
    "final_energy_mwh": 100_000_000,
    "cost_sell_buy_mwh_eur": 0,
}

_grid_lion_battery = {
    "type": StorageType.LI,
    "charging_efficiency": 0.95,
    "discharging_efficiency": 0.95,
    "color": ColorMap.BATTERY,
    "construction_time_years": 1,
    "lifetime_years": 25,
    "discount_rate": 1.05,
    "overnight_costs_per_kw_eur": 548,
    "fixed_o_m_costs_per_kw_eur": 0.7,
    "variable_costs_per_mwh_eur": 5,
    # Be careful to use this as it drastically changes optimization
    # -- moving most costs from capex to opex and thus becomes hesitant
    # to use those batteries.
    # "lifetime_cycles": 3000,
    "initial_energy_ratio": 1.0,
    "reserves": FastReservesProvider(max_installed_fraction=0.5),
}

_heat_distribution = {
    "type": StorageType.HEAT_DISTRIBUTION,
    "color": ColorMap.HEAT_DISTRIBUTION,
    "use": StorageUse.HEAT,
    # Less than 1 to avoid simultaneous charging-discharging.
    "charging_efficiency": 0.999,
    "discharging_efficiency": 1,
    # Loses 6% per hour, or ~77.3% per day.
    "loss_rate_per_day": 0.773,
    "variable_costs_per_mwh_eur": 0,
    "overnight_costs_per_kw_eur": 0,
    "fixed_o_m_costs_per_kw_eur": 0,
}

_heat_pump_as_storage = {
    "type": StorageType.HEAT_PUMP,
    # Consumes electricity, produces heat.
    "use": StorageUse.POWER_TO_HEAT,
    "color": ColorMap.HEAT_PUMPS,
    # No capacity for discharging -- only heat is allowed to be "stored".
    "capacity_mw": 0,
    "min_capacity_mw": 0,
    # Arbitrary -- discharging is neved used. Should not be zero just
    # to be extra careful not to introduce division by zero anywhere.
    "discharging_efficiency": 1,
    # Costs and other economic parameters taken from Danish Energy
    # Agency data sheets, version 16, February 2025. Taking the mean
    # of medium and large air-source heat pumps in 2030. Note that
    # the costs are expressed in terms of the thermal capacity in the
    # data sheet, hence we need to multiply by the COP.
    "construction_time_years": 1,
    "lifetime_years": 25,
    "discount_rate": 1.05,
    "fixed_o_m_costs_per_kw_eur": 8.71,
    "overnight_costs_per_kw_eur": 3522,
    # Variable O&M only; electricity consumption is endogenous.
    "variable_costs_per_mwh_eur": 9.15,
    # No heat storage allowed, the device is only used to transform
    # electricity into heat.
    "max_energy_mwh": 0,
}
"""Heat pump which is technically implemented as a one-way electricity
to heat storage. Charging efficiency is the year-averaged coefficient
of performance -- how much heat is produced per unit of electricity
consumed. It is assumed to be constant throughout the year in the model
(e.g. a large heat pump with a stable source of heat, such as ground
or water)."""

_heat_pump_flexibility = {
    "type": StorageType.HEAT_FLEX,
    # Arbitrary, the color doesn't show up in dispatch charts.
    "color": "black",
    "use": StorageUse.DEMAND_FLEXIBILITY,
    # Less than 1 to avoid simultaneous charging-discharging.
    "charging_efficiency": 0.999,
    "discharging_efficiency": 1,
    "max_capacity_mw_hourly_data_key": Keys.LOAD_HEAT_PUMPS,
    "max_energy_mwh": 0,
    "cycle_length_hours": 6,
    "ramp_rate": 1.0,
    # No costs, assuming natural electricity cost optimization on consumer side.
    "variable_costs_per_mwh_eur": 0,
    "overnight_costs_per_kw_eur": 0,
    "fixed_o_m_costs_per_kw_eur": 0,
}
"""Demand flexibility of heat pumps electricity consumption where the
load may be shifted by up to 3 hours. Additionally, the availability
curve is limited by the Load_Heat_Pumps data column."""

_hot_water_tank = {
    "type": StorageType.HOT_WATER_TANK,
    "color": ColorMap.HOT_WATER_TANKS,
    "use": StorageUse.HEAT,
    # No capacity for discharging -- only heat is allowed to be "stored".
    "capacity_mw": 0,
    "min_capacity_mw": 0,
    # 97% round-trip efficiency.
    "charging_efficiency": 0.98,
    "discharging_efficiency": 0.99,
    # Approx. 5% percent loss per month. Smaller tanks are more lossy.
    "loss_rate_per_day": 1.0 - 0.95 ** (1 / 30),
    # Economic parameters.
    "construction_time_years": 1,
    "lifetime_years": 25,
    "discount_rate": 1.05,
    "fixed_o_m_costs_per_kw_eur": 4,
    "overnight_costs_per_kw_eur": 764,
    "variable_costs_per_mwh_eur": 0,
}

_load_shift_12h = {
    "type": StorageType.LOAD_SHIFT_12H,
    # Arbitrary, the color doesn't show up in dispatch charts.
    "color": "black",
    "use": StorageUse.DEMAND_FLEXIBILITY,
    # Less than 1 to avoid simultaneous charging-discharging.
    "charging_efficiency": 0.999,
    "discharging_efficiency": 1,
    "capacity_mw": 0,
    "capacity_mw_charging": 0,
    "min_capacity_mw": 0,
    "min_capacity_mw_charging": 0,
    "cycle_length_hours": 12,
    # Somewhat arbitrary ramping constraint to preclude sudden jumps.
    "ramp_rate": 0.25,
}

storage_defaults: dict[StorageType, dict] = {
    StorageType.ELECTRIC_BOILER: _electric_boiler_as_storage,
    StorageType.HEAT_DISTRIBUTION: _heat_distribution,
    StorageType.HEAT_FLEX: _heat_pump_flexibility,
    StorageType.HEAT_PUMP: _heat_pump_as_storage,
    StorageType.HOT_WATER_TANK: _hot_water_tank,
    StorageType.HYDROGEN: _grid_hydrogen_storage,
    StorageType.LI: _grid_lion_battery,
    StorageType.LOAD_SHIFT_12H: _load_shift_12h,
    StorageType.LOAD_SHIFT_3H: _load_shift_12h
    | {
        "type": StorageType.LOAD_SHIFT_3H,
        "cycle_length_hours": 3,
        # Shorter-term load shifting may be more flexible.
        "ramp_rate": 1,
    },
}

_storage: dict[str, dict[StorageType, dict]] = {}


def fix_storage_params(storage: dict):
    # Base charging / discharging capacities on nominal_mw.
    nominal_mw = storage.pop("nominal_mw", 0)
    storage.setdefault("capacity_mw", nominal_mw)
    storage.setdefault("capacity_mw_charging", nominal_mw)

    min_nominal_mw = storage.pop("min_nominal_mw", 0)
    storage.setdefault("min_capacity_mw", min_nominal_mw)
    storage.setdefault("min_capacity_mw_charging", min_nominal_mw)

    storage.setdefault("paid_off_capacity_mw_charging", 0)
    # Paid off capacity can't be above min capacity (it is not accounted for in optimization).
    assert (
        storage["paid_off_capacity_mw_charging"] <= storage["min_capacity_mw_charging"]
    ), f"{storage['type']} paid off charging capacity must be below min capacity for optimization"

    # Capacities need to be derived before `fix_source_params` because it sets the
    # (0) default for `min_capacity_mw`.
    storage = fix_source_params(storage)

    # Set trivial default values.
    storage.setdefault("min_charging_capacity_ratio_to_VRE", 0)
    assert (
        storage["min_charging_capacity_ratio_to_VRE"] >= 0
    ), "cannot force negative ratio"
    storage.setdefault("use", StorageUse.ELECTRICITY)
    storage.setdefault("separate_charging", None)
    storage.setdefault("loss_rate_per_day", 0)
    assert storage["loss_rate_per_day"] < 1, "cannot lose more than 100%"
    storage.setdefault("use_mwh_per_day", 0)

    storage.setdefault("initial_energy_mwh", 0)
    storage.setdefault("final_energy_mwh", 0)
    storage.setdefault("cycle_length_hours", None)

    if cycle_length := storage["cycle_length_hours"]:
        if not isinstance(cycle_length, int):
            raise ValueError("Storage cycle length must be an integer")
        if 8760 % cycle_length != 0:
            logger.warning(
                "Cycle length should divide the year (8760 hours) evenly."
                f" {cycle_length}-hour cycle of {storage['type'].value} does not."
            )

    storage.setdefault("cost_sell_buy_mwh_eur", 0)
    storage.setdefault("ramp_rate", 1)
    storage.setdefault("inflow_hourly_data_key", None)
    storage.setdefault("inflow_min_discharge_ratio", None)
    storage.setdefault("max_capacity_mw_hourly_data_key", None)
    storage.setdefault(
        "max_capacity_charging_mw_hourly_data_key",
        storage["max_capacity_mw_hourly_data_key"],
    )
    storage.setdefault("max_capacity_mw_factor", None)

    # Unless explicitly specified, `min_final_energy_mwh` mirrors `final_energy_mwh`.
    storage.setdefault("min_final_energy_mwh", storage["final_energy_mwh"])

    # Base max_energy_mwh on max_energy_hours.
    max_energy_hours = storage.pop("max_energy_hours", None)
    if max_energy_hours is not None:
        nominal_mw_discharging = storage["capacity_mw"]
        storage["max_energy_mwh"] = nominal_mw_discharging * max_energy_hours

    initial_energy_ratio = storage.pop("initial_energy_ratio", None)
    if initial_energy_ratio is not None:
        storage["initial_energy_mwh"] = storage["max_energy_mwh"] * initial_energy_ratio

    # Construct separate charging cost profile.
    if storage["separate_charging"] is not None:
        economics_dict = extract_economics_params(storage["separate_charging"])
        economics = SourceEconomics(**economics_dict)
        storage["separate_charging"] = economics

    # Base overnight_costs_per_kw_eur on cost per kwh of max_energy and on (discharging) capacity.
    overnight_costs_per_kwh_eur = storage.pop("overnight_costs_per_kwh_eur", None)
    if overnight_costs_per_kwh_eur is not None:
        kwh_per_kw = storage["max_energy_mwh"] / storage["capacity_mw"]
        storage["overnight_costs_per_kw_eur"] = overnight_costs_per_kwh_eur * kwh_per_kw

    lifetime_cycles = storage.pop("lifetime_cycles", None)
    if lifetime_cycles is not None:
        max_energy_mwh = storage["max_energy_mwh"]
        discharging_mw = storage["capacity_mw"]
        discharging_efficiency = storage["discharging_efficiency"]
        draining_mw = discharging_mw / discharging_efficiency
        hours_for_full_cycle = max_energy_mwh / draining_mw
        storage["lifetime_hours"] = lifetime_cycles * hours_for_full_cycle

    return storage


def get_storage(storage: Union[str, dict[StorageType, dict]]):
    if isinstance(storage, str):
        storages = deepcopy(_storage[storage])
    else:
        storages = deepcopy(storage)

    def create_storage(key: StorageType, params_add: dict) -> Storage:
        storage_dict = fix_storage_params(storage_defaults.get(key, {}) | params_add)
        economics = SourceEconomics(**extract_economics_params(storage_dict))
        return Storage(economics=economics, **storage_dict)

    return {key: create_storage(key, params) for key, params in storages.items()}

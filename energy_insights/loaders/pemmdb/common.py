from typing import Optional

from ...grid_plot_utils import Keys

# TODO: Avoid private access.
from ...params_library.storage import (
    __hydro_pecd,
    __pecd_hydro_fill_ratio,
    __pumped_hydro_closed_pecd,
    __pumped_hydro_open_pecd,
    __reservoir_pecd,
    __ror_pecd,
)
from ...region import *
from ...sources.storage import StorageType

# Deal with differences in country codes vs. PEMMDB dataset.
PEMMDB_COUNTRY_MAP: dict[Zone, Region] = {GREAT_BRITAIN: Region("UK")}


def make_battery(
    capacity_mw: float,
    capacity_mw_charging: float,
    max_energy_mwh: float,
    allow_capex_optimization=False,
) -> Optional[dict]:
    if max_energy_mwh == 0:
        return

    return {
        "capacity_mw": capacity_mw,
        "capacity_mw_charging": capacity_mw_charging,
        "max_energy_mwh": max_energy_mwh,
        "min_capacity_mw": 0 if allow_capex_optimization else capacity_mw,
        "min_capacity_mw_charging": (
            0 if allow_capex_optimization else capacity_mw_charging
        ),
    }


def make_pondage_hydro(capacity_mw: float, max_energy_mwh: float) -> Optional[dict]:
    if capacity_mw == 0:
        return

    return __hydro_pecd | {
        "type": StorageType.PONDAGE,
        "inflow_hourly_data_key": Keys.HYDRO_INFLOW_PONDAGE,
        "max_energy_mwh": max_energy_mwh,
        "initial_energy_mwh": __pecd_hydro_fill_ratio * max_energy_mwh,
        "final_energy_mwh": __pecd_hydro_fill_ratio * max_energy_mwh,
        "capacity_mw": capacity_mw,
        "min_capacity_mw": capacity_mw,
        # Tiny variable costs, similar to run-of-river.
        "variable_costs_per_mwh_eur": 2,
    }


def make_pumped_hydro(
    capacity_mw: float, capacity_mw_charging: float, max_energy_mwh: float, open: bool
) -> Optional[dict]:
    if max_energy_mwh == 0:
        return

    template = __pumped_hydro_open_pecd if open else __pumped_hydro_closed_pecd

    return template | {
        "max_energy_mwh": max_energy_mwh,
        "initial_energy_mwh": __pecd_hydro_fill_ratio * max_energy_mwh,
        "final_energy_mwh": __pecd_hydro_fill_ratio * max_energy_mwh,
        "capacity_mw": capacity_mw,
        "min_capacity_mw": capacity_mw,
        "capacity_mw_charging": capacity_mw_charging,
        "min_capacity_mw_charging": capacity_mw_charging,
    }


def make_reservoir_hydro(capacity_mw: float, max_energy_mwh: float) -> Optional[dict]:
    if max_energy_mwh == 0:
        return

    return __reservoir_pecd | {
        "inflow_min_discharge_ratio": 0.4,
        "max_energy_mwh": max_energy_mwh,
        "initial_energy_mwh": __pecd_hydro_fill_ratio * max_energy_mwh,
        "final_energy_mwh": __pecd_hydro_fill_ratio * max_energy_mwh,
        "capacity_mw": capacity_mw,
        "min_capacity_mw": capacity_mw,
    }


def make_ror_hydro(capacity_mw: float) -> Optional[dict]:
    if capacity_mw == 0:
        return

    return __ror_pecd | {
        # Approximately the minimum constraint (vs. average inflows)
        # in Norwegian inflows data.
        "inflow_min_discharge_ratio": 0.3,
        "max_energy_mwh": 0,
        "capacity_mw": capacity_mw,
        "min_capacity_mw": capacity_mw,
    }


def map_to_pemmdb_region(country: Zone) -> Region:
    return PEMMDB_COUNTRY_MAP.get(country, country)


def zone_to_country(zone: str) -> str:
    return zone[:2]

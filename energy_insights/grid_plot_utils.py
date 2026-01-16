"""
Provides utils for grid plots.
"""

import math
from typing import Union

import pandas as pd

from .data_keys import Keys
from .region import Region
from .sources.basic_source import BasicSourceType
from .sources.flexible_source import FlexibleSource, FlexibleSourceType
from .sources.storage import Storage

__summer_start_day = math.ceil(365 / 4)
__summer_end_day = math.ceil(3 * 365 / 4)


def get_summer_slice(data: pd.DataFrame):
    return data[
        (data.index.day_of_year >= __summer_start_day)
        & (data.index.day_of_year < __summer_end_day)
    ]


def get_winter_slice(data: pd.DataFrame):
    return data[
        (data.index.day_of_year < __summer_start_day)
        | (data.index.day_of_year >= __summer_end_day)
    ]


def split_excess_production(data: pd.DataFrame):
    net_export = -data[Keys.NET_IMPORT]
    consumption = data[Keys.LOAD] + net_export
    if "Charging" in data:
        consumption += data["Charging"] - data["Discharging"]

    # Use a temp data frame to store residuals and to clip data with such residuals.
    residual = (consumption - data["Nuclear"] - data["Hydro"]).clip(lower=0)
    tmp = pd.DataFrame(
        data={"ResidualForVRE": residual, "VRE": data["VRE"]}, index=data.index
    )
    used_vre = tmp[["VRE", "ResidualForVRE"]].min(axis=1)
    excess_vre = (tmp["VRE"] - tmp["ResidualForVRE"]).clip(lower=0)

    for source in {
        BasicSourceType.SOLAR,
        BasicSourceType.OFFSHORE,
        BasicSourceType.ONSHORE,
        BasicSourceType.WIND,
    }:
        key = get_basic_key(source)
        data[get_basic_used_key(source)] = used_vre * (data[key] / data["VRE"])
        data[get_basic_excess_key(source)] = excess_vre * (data[key] / data["VRE"])


def get_grid_balance(
    data: pd.DataFrame, flexible_sources: dict[FlexibleSourceType, FlexibleSource]
):
    twh_in_mwh = 1000000

    def get_sum(df, source_key):
        return df[source_key].sum() / twh_in_mwh

    def get_clipped_sum(df: pd.DataFrame, source_key: str, clip_key: str) -> float:
        return df[[source_key, clip_key]].min(axis=1).sum() / twh_in_mwh

    # Use a temp data frame to store residuals and to clip sums with such residuals.
    residual_for_hydro = (data[Keys.LOAD] - data["Nuclear"]).clip(lower=0)
    tmp = pd.DataFrame(
        index=data.index,
        data={
            "ResidualForHydro": residual_for_hydro,
            "ResidualForFlexible": (
                residual_for_hydro - data["Hydro"] - data["VRE"]
            ).clip(lower=0),
            "Hydro": data["Hydro"],
        },
    )

    load = get_sum(data, Keys.LOAD)
    nuclear = get_clipped_sum(data, "Nuclear", Keys.LOAD)
    hydro = get_clipped_sum(tmp, "Hydro", "ResidualForHydro")

    wind = get_sum(data, get_basic_used_key(BasicSourceType.WIND))
    solar = get_sum(data, get_basic_used_key(BasicSourceType.SOLAR))
    excess_wind = get_sum(data, get_basic_excess_key(BasicSourceType.WIND))
    excess_solar = get_sum(data, get_basic_excess_key(BasicSourceType.SOLAR))

    # This results in plotting _net_ import / export, consistently with weekly plots. This is needed
    # for aggregate plots but can be somewhat misleading in separate plots with transit countries.
    # TODO: Allow to configure whether we show the whole balance or just net import / export in each
    # hour.
    tmp[Keys.NET_IMPORT] = data[Keys.NET_IMPORT].clip(lower=0)

    inflow = get_clipped_sum(tmp, Keys.NET_IMPORT, "ResidualForFlexible")
    tmp["ResidualForFlexible"] = (
        tmp["ResidualForFlexible"] - tmp[Keys.NET_IMPORT]
    ).clip(lower=0)

    flexible: dict[FlexibleSourceType, float] = {}
    for key, flexible_source in flexible_sources.items():
        data_key = get_flexible_key(flexible_source)
        tmp[data_key] = data[data_key]
        flexible[key] = get_clipped_sum(tmp, data_key, "ResidualForFlexible")
        tmp["ResidualForFlexible"] = (tmp["ResidualForFlexible"] - tmp[data_key]).clip(
            lower=0
        )

    discharging = 0
    charging = 0
    if "Charging" in data:
        discharging = get_sum(data, "Discharging")
        charging = get_sum(data, "Charging")

    # This is also _net_ export.
    tmp[Keys.EXPORT] = data[Keys.NET_IMPORT].clip(upper=0)
    # Return export as a positive value.
    outflow = -1 * get_sum(tmp, Keys.EXPORT)

    return (
        load,
        nuclear,
        hydro,
        wind,
        solar,
        inflow,
        flexible,
        discharging,
        charging,
        outflow,
        excess_solar,
        excess_wind,
    )


def get_residual_load(data: pd.DataFrame):
    # Get just the two relevant columns and sort them by residual load.
    df = data.loc[:, ["Residual"]].sort_values(by=["Residual"], ascending=False)
    # Add an "index" based on this new sorting.
    year_hours = df.shape[0]
    df["Index"] = range(0, year_hours)
    return df


def get_small_threshold():
    # Linear optimization stops with some error in the order of W, ignore values up to 1 kW.
    return 0.001


def has_excess(data) -> bool:
    # Approximate zero price as Nuclear + Hydro covers the residual load.
    return (data["Nuclear"] + data["Hydro"]) - data["Residual"] > get_small_threshold()


def has_curtailment(data) -> bool:
    return data["Curtailment"] > get_small_threshold()


def get_storable_curtailment_shortage(data: pd.DataFrame):
    return (
        data[has_excess(data) & ~has_curtailment(data)],
        data[has_excess(data) & has_curtailment(data)],
        data[~has_excess(data)],
    )


def get_basic_key(type: BasicSourceType):
    if type is BasicSourceType.SOLAR:
        return Keys.SOLAR
    elif type is BasicSourceType.OFFSHORE:
        return Keys.WIND_OFFSHORE
    elif type is BasicSourceType.ONSHORE:
        return Keys.WIND_ONSHORE
    elif type is BasicSourceType.WIND:
        return Keys.WIND
    elif type is BasicSourceType.NUCLEAR:
        return Keys.NUCLEAR
    elif type is BasicSourceType.HYDRO:
        return Keys.HYDRO
    assert False, "unsupported type of production " + type.name


def get_basic_used_key(type: BasicSourceType):
    return f"{get_basic_key(type)}_Used"


def get_basic_excess_key(type: BasicSourceType):
    return f"{get_basic_key(type)}_Excess"


def get_flexible_basic_predefined_key(type: BasicSourceType):
    return f"{get_basic_key(type)}_Predefined"


def get_flexible_basic_decrease_key(type: BasicSourceType):
    return f"{get_basic_key(type)}_Decrease"


def get_flexible_key(flexible_source: FlexibleSource):
    return f"Flexible_{flexible_source.type.value}"


def get_flexible_electricity_equivalent_key(flexible_source: FlexibleSource):
    return f"Electricity_Equivalent_Flexible_{flexible_source.type.value}"


def get_flexible_heat_key(flexible_source: FlexibleSource):
    return f"Heat_Flexible_{flexible_source.type.value}"


def get_charging_key(storage: Storage):
    return f"Charging_{storage.type.value}"


def get_discharging_key(storage: Storage):
    return f"Discharging_{storage.type.value}"


def get_state_of_charge_key(storage: Storage):
    return f"State_Of_Charge_{storage.type.value}"


def get_import_key(country_from: Region):
    return f"Import_{country_from}"


def get_export_key(country_to: Region):
    return f"Export_{country_to}"


def get_p2h_heat_key(storage: Storage):
    return f"Heat_P2H_{storage.type.value}"


def get_ramp_up_key(type: Union[BasicSourceType, FlexibleSourceType]) -> str:
    if isinstance(type, BasicSourceType):
        key = get_basic_key(type)
    else:
        key = type.value

    return f"Ramp_Up_{key}"

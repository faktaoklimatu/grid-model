from functools import cache, cached_property
from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas

from ...region import Region, Zone
from ...sources.basic_source import BasicSourceType
from ...sources.flexible_source import FlexibleSourceType
from ...sources.reserves import ReservesRequirements
from ...sources.storage import StorageType

from .common import (
    map_to_pemmdb_region,
    make_battery,
    make_pondage_hydro,
    make_pumped_hydro,
    make_reservoir_hydro,
    make_ror_hydro,
    zone_to_country,
)
from .pemmdb_2023 import Pemmdb2023Loader

# Raw datasets downloaded from the ERAA 2024 stakeholder interactions
# page[1], section "ERAA 2024: Preliminary input data following the
# call-for-evidence".
#
# PEMMDB stands for "Pan-European Market Database". It is maintained by
# the System Adequacy and Market Modelling working group[2] (WG SAMM) at
# ENTSO-E. ERAA stands for "European Resource Adequacy Assessment".
#
# [1]: https://www.entsoe.eu/outlooks/eraa/stakeholder-interactions/
# [2]: https://docstore.entsoe.eu/about-entso-e/system-development/system-adequacy-and-market-modeling/Pages/default.aspx


_PEMMDB_2024_BASIC_SOURCES_MAP: dict[str, BasicSourceType] = {
    "Nuclear": BasicSourceType.NUCLEAR,
    "Solar (PV)": BasicSourceType.SOLAR,
    "Wind offshore": BasicSourceType.OFFSHORE,
    "Wind onshore": BasicSourceType.ONSHORE,
}

_PEMMDB_2024_FLEXIBLE_SOURCES_MAP: dict[str, tuple[FlexibleSourceType, dict]] = {
    "Biofuel": (
        FlexibleSourceType.BIOGAS,
        {"uptime_ratio": 0.8, "overnight_costs_per_kw_eur": 1800},
    ),
    "DSR": (FlexibleSourceType.DSR, {}),
    "Gas": (FlexibleSourceType.GAS_CCGT, {}),
    "Hard coal": (FlexibleSourceType.COAL, {}),
    "Lignite": (FlexibleSourceType.LIGNITE, {}),
    # TODO: Can we map this more precisely?
    "Oil": (FlexibleSourceType.GAS_ENGINE, {}),
    # This can be country-specific, e.g. mostly lig_ex/lig_bp in Czechia,
    # but gas_peak in Norway.
    "Others (non-RES)": (FlexibleSourceType.LIGNITE_EXTRACTION, {}),
    "Others (RES)": (
        FlexibleSourceType.BIOGAS_PEAK,
        {"uptime_ratio": 0.8, "overnight_costs_per_kw_eur": 970},
    ),
    "Small biomass": (
        FlexibleSourceType.SOLID_BIOMASS,
        {"uptime_ratio": 0.8, "overnight_costs_per_kw_eur": 1800},
    ),
    # TODO: Map FuelCell and Hydrogen to something hydrogen-adjacent.
    # TODO: Can we map Geothermal (so far mostly in Italy only) in a useful way?
}


class Pemmdb2024Loader(Pemmdb2023Loader):
    """
    Loader for the preliminary 2024 edition of the Pan-European Market
    Modelling Database (PEMMDB). This dataset is prepared regularly for
    the modelling needs of the European Resource Adequacy Assessment
    (ERAA).
    """

    _EDITION = 2024
    _TARGET_YEARS = (2026, 2028, 2030, 2035)

    _BASIC_SOURCES_MAP = _PEMMDB_2024_BASIC_SOURCES_MAP
    _FLEXIBLE_SOURCES_MAP = _PEMMDB_2024_FLEXIBLE_SOURCES_MAP

    def __init__(self, data_directory: Union[str, Path]) -> None:
        data_directory = Path(data_directory)
        self._data_file_capacities = (
            data_directory / "ERAA2024 GenerationCapacities.csv"
        )
        self._data_file_hydro = data_directory / "ERAA2024 Hydro capacities.csv"
        self._data_file_reserves = data_directory / "ERAA2024 Reserves Requirements.csv"
        self._data_file_storage = data_directory / "ERAA2024 Storage.csv"

    def _data_file_intercon(self, year: int) -> Path:
        data_directory = self._data_file_capacities.parent
        # FIXME: Temporary workaround for coal study re-run.
        year = 2030
        return data_directory / f"ERAA2024 NTCs TY{year}.xlsx"

    @cached_property
    def _df_hydro(self) -> pandas.DataFrame:
        """Dataset of hydro capacities."""
        _columns = ["COUNTRY", "YEAR", "TECHNOLOGY"]

        df_raw = pandas.read_csv(self._data_file_hydro).rename(
            columns={
                "MAX TURBINE CAP (MW)": "CAPACITY_MW",
                "MAX PUMPING CAP (MW)": "CAPACITY_MW_CHARGING",
                "TARGET_YEAR": "YEAR",
            }
        )
        df_raw["COUNTRY"] = df_raw["MARKET_NODE"].apply(zone_to_country)

        df_hydro = (
            df_raw[_columns + ["CAPACITY_MW", "CAPACITY_MW_CHARGING"]]
            .groupby(_columns)
            .sum()
        )

        # Merge with hydro part of storage dataset to create a single
        # DataFrame with capacities as well as energy content.
        df_merged = pandas.merge(
            df_hydro,
            self._df_storage.loc[:, :, "Hydro", :],
            how="outer",
            left_index=True,
            right_index=True,
        ).fillna(0)

        return df_merged

    @cache
    def _df_intercon(self, year: int) -> pandas.DataFrame:
        self._check_year(year)

        # Load AC and DC links separately and sum their capacities.
        df_hvac = self._load_intercon_from_sheet_body(year, "HVAC")
        df_hvdc = self._load_intercon_from_sheet_body(year, "HVDC")

        return df_hvac.add(df_hvdc, fill_value=0)

    @cached_property
    def _df_reserves(self) -> pandas.DataFrame:
        """Dataset of reserve capacity requirements."""
        _columns = ["COUNTRY", "YEAR", "TECHNOLOGY"]

        df_raw = pandas.read_csv(self._data_file_reserves).rename(
            columns={"RESERVES[MW]": "CAPACITY_MW", "TECHNOLOGY_DETAILED": "TECHNOLOGY"}
        )
        df_raw["COUNTRY"] = df_raw["MARKET_NODE"].apply(zone_to_country)

        return (
            df_raw[(df_raw["DATA_VERSION"] == "Post-CfE")][_columns + ["CAPACITY_MW"]]
            .groupby(_columns)
            .sum()
        )

    @cached_property
    def _df_sources(self) -> pandas.DataFrame:
        """Dataset of installed capacities of generation technologies."""
        _columns = ["COUNTRY", "YEAR", "TECHNOLOGY"]

        df_raw = pandas.read_csv(self._data_file_capacities).rename(
            columns={"TARGET_YEAR": "YEAR"}
        )
        df_raw["COUNTRY"] = df_raw["MARKET_NODE"].apply(zone_to_country)

        return (
            df_raw[(df_raw["DATA_VERSION"] == "Post-CfE")][_columns + ["CAPACITY_MW"]]
            .groupby(_columns)
            .sum()
        )

    @cached_property
    def _df_storage(self) -> pandas.DataFrame:
        """Dataset of storage capacities (including hydro)."""
        _columns = ["COUNTRY", "YEAR", "GROUP", "TECHNOLOGY"]

        df_raw = (
            pandas.read_csv(self._data_file_storage)
            .rename(columns={"TECHNOLOGY": "GROUP", "TYPE_STORAGE": "TECHNOLOGY"})
            .replace(
                {
                    "TECHNOLOGY": {
                        "CL pumping": "Closed loop pumping",
                        "OL pumping": "Open loop pumping",
                    }
                }
            )
        )
        df_raw["COUNTRY"] = df_raw["MARKET_NODE"].apply(zone_to_country)
        df_raw["MAX_ENERGY_MWH"] = df_raw["VALUE"] * np.where(
            df_raw["UNIT"] == "TWh", 1e6, 1e3
        )

        return (
            df_raw[(df_raw["DATA_VERSION"] == "Post-CfE")][
                _columns + ["MAX_ENERGY_MWH"]
            ]
            .groupby(_columns)
            .sum()
        )

    def _load_hydro(self, pemmdb_country: Region, year: int) -> dict[StorageType, dict]:
        if (pemmdb_country, year) not in self._df_hydro.index:
            return {}

        storages: dict[StorageType, dict] = {}
        df_hydro = self._df_hydro.loc[(pemmdb_country, year)]

        if "Run of river" in df_hydro.index:
            capacity_mw = df_hydro.loc["Run of river"]["CAPACITY_MW"]
            ror = make_ror_hydro(capacity_mw)
            if ror:
                storages[StorageType.ROR] = ror

        if "Pondage" in df_hydro.index:
            capacity_mw = df_hydro.loc["Pondage"]["CAPACITY_MW"]
            max_energy_mwh = df_hydro.loc["Pondage"]["MAX_ENERGY_MWH"]
            pondage = make_pondage_hydro(capacity_mw, max_energy_mwh)
            if pondage:
                storages[StorageType.PONDAGE] = pondage

        if "Open loop pumping" in df_hydro.index:
            capacity_mw = df_hydro.loc["Open loop pumping"]["CAPACITY_MW"]
            capacity_mw_charging = df_hydro.loc["Open loop pumping"].get(
                "CAPACITY_MW_CHARGING", capacity_mw
            )
            max_energy_mwh = df_hydro.loc["Open loop pumping"]["MAX_ENERGY_MWH"]
            if pumped_open := make_pumped_hydro(
                capacity_mw, capacity_mw_charging, max_energy_mwh, open=True
            ):
                storages[StorageType.PUMPED_OPEN] = pumped_open

        if "Closed loop pumping" in df_hydro.index:
            capacity_mw = df_hydro.loc["Closed loop pumping"]["CAPACITY_MW"]
            capacity_mw_charging = df_hydro.loc["Closed loop pumping"].get(
                "CAPACITY_MW_CHARGING", capacity_mw
            )
            max_energy_mwh = df_hydro.loc["Closed loop pumping"]["MAX_ENERGY_MWH"]
            if pumped_closed := make_pumped_hydro(
                capacity_mw, capacity_mw_charging, max_energy_mwh, open=False
            ):
                storages[StorageType.PUMPED] = pumped_closed

        if "Reservoir" in df_hydro.index:
            capacity_mw = df_hydro.loc["Reservoir"]["CAPACITY_MW"]
            max_energy_mwh = df_hydro.loc["Reservoir"]["MAX_ENERGY_MWH"]
            reservoir = make_reservoir_hydro(capacity_mw, max_energy_mwh)
            if reservoir:
                storages[StorageType.RESERVOIR] = reservoir

        return storages

    def get_flexible_sources(
        self, country: Zone, year: int, allow_capex_optimization=False
    ) -> dict[FlexibleSourceType, dict]:
        pemmdb_country = map_to_pemmdb_region(country)
        sources: dict[FlexibleSourceType, dict] = {}

        try:
            df_sources = self._df_sources.loc[(pemmdb_country, year)]
        except KeyError:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ with TY {year} not available in PEMMDB dataset"
            )

        for pemmdb_key, (
            source_type,
            template,
        ) in self._FLEXIBLE_SOURCES_MAP.items():
            pemmdb_keys = df_sources.index.intersection(pemmdb_key.split("|"))
            if pemmdb_keys.empty:
                continue
            installed_mw = float(df_sources.loc[pemmdb_keys, "CAPACITY_MW"].sum())
            # Ignore sources below 100 kW.
            if installed_mw < 0.1:
                continue
            source = template | {
                "capacity_mw": installed_mw,
                "min_capacity_mw": 0 if allow_capex_optimization else installed_mw,
            }
            sources[source_type] = source

        return sources

    def get_installed(self, country: Zone, year: int) -> dict[BasicSourceType, float]:
        pemmdb_country = map_to_pemmdb_region(country)
        sources: dict[BasicSourceType, float] = {}

        # TODO: How to correctly map "Implicit solar PV" (165 GW in Germany in 2035)?
        _implicit_solar_key = "Implicit solar PV"

        try:
            df_sources = self._df_sources.loc[(pemmdb_country, year)]
        except KeyError:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ with TY {year} not available in PEMMDB dataset"
            )

        for pemmdb_key, source_type in self._BASIC_SOURCES_MAP.items():
            if pemmdb_key not in df_sources.index:
                continue
            installed_mw = df_sources.loc[pemmdb_key].iloc[0]
            sources[source_type] = installed_mw / 1000

            # Bundle implicit solar PV together with "standard" solar
            # PV if available.
            if pemmdb_key == "Solar (PV)" and _implicit_solar_key in df_sources.index:
                installed_mw = df_sources.loc[_implicit_solar_key].iloc[0]
                sources[source_type] += installed_mw / 1000

        return sources

    def get_reserve_requirements(
        self, country: Zone, year: int
    ) -> Optional[ReservesRequirements]:
        raise NotImplementedError("Reserves requirements not implement for PEMMDB 2024")

    def get_storage(
        self, country: Zone, year: int, allow_capex_optimization=False
    ) -> dict[StorageType, dict]:
        pemmdb_country = map_to_pemmdb_region(country)
        storages: dict[StorageType, dict] = {}

        try:
            df_sources = self._df_sources.loc[(pemmdb_country, year)]
            df_storage = self._df_storage.loc[(pemmdb_country, year)]
        except KeyError:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ with TY {year} not available in PEMMDB dataset"
            )

        if "Battery" in df_sources.index:
            capacity_mw = df_sources.loc["Battery"]["CAPACITY_MW"]
            # TODO: What to do with "Non-market batteries" in ERAA 2024?
            # We're summing them into the market for now.
            max_energy_mwh = df_storage.loc["Batteries"]["MAX_ENERGY_MWH"].sum()
            batteries = make_battery(
                capacity_mw, capacity_mw, max_energy_mwh, allow_capex_optimization
            )
            if batteries:
                storages[StorageType.LI] = batteries

        storages |= self._load_hydro(pemmdb_country, year)

        return storages

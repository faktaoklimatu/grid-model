from collections import defaultdict
from collections.abc import Collection
from functools import cache, cached_property
from pathlib import Path
from typing import Any, Optional, Union

import pandas

from ...params_library.interconnectors import (
    InterconnectorsDict,
    add_distances_type_and_loss_to_interconnectors,
    aggregate_interconnectors,
    get_aggregated_countries,
)
from ...params_library.load_factors import LoadFactors
from ...region import AggregateRegion, Region, Zone
from ...sources.basic_source import BasicSourceType, ProfileOverride
from ...sources.flexible_source import FlexibleSourceType
from ...sources.reserves import ReservesRequirements
from ...sources.storage import StorageType

from .common import (
    PEMMDB_COUNTRY_MAP,
    map_to_pemmdb_region,
    make_battery,
    make_pondage_hydro,
    make_pumped_hydro,
    make_reservoir_hydro,
    make_ror_hydro,
    zone_to_country,
)

# Dataset "PEMMDB Generation" downloaded from the ENTSO-E ERAA
# 2023 page[1].
#
# PEMMDB stands for "Pan-European Market Database". It is maintained by
# the System Adequacy and Market Modelling working group[2] (WG SAMM) at
# ENTSO-E. ERAA stands for "European Resource Adequacy Assessment".
#
# [1]: https://www.entsoe.eu/outlooks/eraa/2023/eraa-downloads/
# [2]: https://docstore.entsoe.eu/about-entso-e/system-development/system-adequacy-and-market-modeling/Pages/default.aspx

_PEMMDB_2023_BASIC_SOURCES_MAP: dict[str, BasicSourceType] = {
    # NOTE: At the moment, we load hydro parameters from
    # the pre-processed PECD dataset rather than from PEMMDB.
    "Nuclear": BasicSourceType.NUCLEAR,
    "Solar (Photovoltaic)": BasicSourceType.SOLAR,
    "Wind Offshore": BasicSourceType.OFFSHORE,
    "Wind Onshore": BasicSourceType.ONSHORE,
}

_PEMMDB_2023_FLEXIBLE_SOURCES_MAP: dict[str, tuple[FlexibleSourceType, dict]] = {
    "Biofuel": (
        FlexibleSourceType.SOLID_BIOMASS,
        {"uptime_ratio": 0.8, "overnight_costs_per_kw_eur": 1800},
    ),
    "Demand Side Response capacity": (FlexibleSourceType.DSR, {}),
    # NOTE: The trailing space is intentional.
    "Gas ": (FlexibleSourceType.GAS_CCGT, {}),
    "Hard Coal": (FlexibleSourceType.COAL, {}),
    "Lignite": (FlexibleSourceType.LIGNITE, {}),
    # TODO: Can we map this more precisely?
    "Oil": (FlexibleSourceType.GAS_ENGINE, {}),
    # This can be country-specific, e.g. mostly lig_ex/lig_bp in Czechia,
    # but gas_peak in Norway.
    "Others non-renewable": (FlexibleSourceType.LIGNITE_EXTRACTION, {}),
    "Others renewable": (
        FlexibleSourceType.BIOGAS,
        {"uptime_ratio": 0.8, "overnight_costs_per_kw_eur": 970},
    ),
}


def _pemmdb_load_batteries(
    sources: pandas.Series, storage: pandas.Series, allow_capex_optimization: bool
) -> Optional[dict]:
    installed_mw_charging = sources["Batteries (Injection)"]
    installed_mw_discharging = sources["Batteries (Offtake)"]
    max_energy_mwh = storage["Batteries"]

    return make_battery(
        installed_mw_discharging,
        installed_mw_charging,
        max_energy_mwh,
        allow_capex_optimization,
    )


def _pemmdb_load_pondage_hydro(
    sources: pandas.Series, storage: pandas.Series
) -> Optional[dict]:
    capacity_mw = sources["Hydro - Pondage (Turbine)"]
    max_energy_mwh = storage["Hydro - Pondage"]

    return make_pondage_hydro(capacity_mw, max_energy_mwh)


def _pemmdb_load_pumped_hydro(
    sources: pandas.Series, storage: pandas.Series
) -> dict[StorageType, dict]:
    def _make_storage_dict(name: str, open: bool) -> Optional[dict]:
        capacity_mw = sources[f"{name} (Turbine)"]
        capacity_mw_charging = -1 * sources[f"{name} (Pumping)"]
        max_energy_mwh = storage[name]

        return make_pumped_hydro(
            capacity_mw, capacity_mw_charging, max_energy_mwh, open
        )

    storages: dict[StorageType, dict] = {}

    # Load open- and closed-loop pumped hydro separately as closed-loop
    # has no natural inflows.
    if pumped_open := _make_storage_dict("Hydro - Pump Storage Open Loop", open=True):
        storages[StorageType.PUMPED_OPEN] = pumped_open
    if pumped_closed := _make_storage_dict(
        "Hydro - Pump Storage Closed Loop", open=False
    ):
        storages[StorageType.PUMPED] = pumped_closed

    return storages


def _pemmdb_load_reservoir_hydro(
    sources: pandas.Series, storage: pandas.Series
) -> Optional[dict]:
    capacity_mw = sources["Hydro - Reservoir (Turbine)"]
    max_energy_mwh = storage["Hydro - Reservoir"]

    return make_reservoir_hydro(capacity_mw, max_energy_mwh)


def _pemmdb_load_ror_hydro(sources: pandas.Series) -> Optional[dict]:
    capacity_mw = sources["Hydro - Run of River (Turbine)"]

    return make_ror_hydro(capacity_mw)


class Pemmdb2023Loader:
    """
    Loader for the 2023 edition of the Pan-European Market Modelling
    Database (PEMMDB). This dataset is prepared regularly for the
    modelling needs of the European Resource Adequacy Assessment (ERAA).
    """

    _EDITION = 2023
    _TARGET_YEARS = (2025, 2028, 2030, 2033)

    _BASIC_SOURCES_MAP = _PEMMDB_2023_BASIC_SOURCES_MAP
    _FLEXIBLE_SOURCES_MAP = _PEMMDB_2023_FLEXIBLE_SOURCES_MAP

    _INTERCON_NUM_ROWS = 3
    _INTERCON_SKIP_ROWS = 7
    _RESERVES_SHEET_NAME = "Reserve Requirements"
    _SOURCES_NUM_ROWS = 24
    _SOURCES_SKIP_ROWS = 1
    _STORAGE_NUM_ROWS = 6
    _STORAGE_SKIP_ROWS = 28

    def __init__(self, data_file: Union[str, Path]) -> None:
        self._data_file = Path(data_file)

    @classmethod
    def _check_year(cls, year: int) -> None:
        if year not in cls._TARGET_YEARS:
            available_years = ", ".join(map(str, cls._TARGET_YEARS))
            raise ValueError(
                f"Target year {year} not available in PEMMDB {cls._EDITION} dataset. "
                f"Available years: {available_years}"
            )

    def _data_file_intercon(self, year: int) -> Path:
        data_directory = self._data_file.parent
        return data_directory / f"PEMMDB_Transfer_Capacities_{year}.xlsx"

    @cache
    def _df_intercon(self, year: int) -> pandas.DataFrame:
        Pemmdb2023Loader._check_year(year)

        # Load AC and DC links separately and sum their capacities.
        df_hvac = self._load_intercon_from_sheet_body(year, "HVAC")
        df_hvdc = self._load_intercon_from_sheet_body(year, "HVDC")

        return df_hvac.add(df_hvdc, fill_value=0)

    @cached_property
    def _df_reserves(self) -> pandas.DataFrame:
        df_raw = pandas.read_excel(
            self._data_file,
            sheet_name=Pemmdb2023Loader._RESERVES_SHEET_NAME,
            index_col=[0, 1],
            engine="openpyxl",
        )
        return df_raw.groupby(lambda key: (zone_to_country(key[0]), key[1])).sum()

    @cache
    def _df_sources(self, year: int) -> pandas.DataFrame:
        Pemmdb2023Loader._check_year(year)

        df_raw = pandas.read_excel(
            self._data_file,
            sheet_name=self._sheet_name(year),
            usecols="B:BE",
            skiprows=Pemmdb2023Loader._SOURCES_SKIP_ROWS,
            nrows=Pemmdb2023Loader._SOURCES_NUM_ROWS,
            index_col=0,
            engine="openpyxl",
        )
        # The index (first column in the spreadsheet) lists something
        # like bidding zones with the first two characters being
        # the country code, so we sum all the columns (installed
        # capacities) across these country codes.
        return df_raw.transpose().groupby(zone_to_country).sum()

    @cache
    def _df_storage(self, year: int) -> pandas.DataFrame:
        Pemmdb2023Loader._check_year(year)

        df_raw = pandas.read_excel(
            self._data_file,
            sheet_name=self._sheet_name(year),
            usecols="B:BE",
            skiprows=Pemmdb2023Loader._STORAGE_SKIP_ROWS,
            nrows=Pemmdb2023Loader._STORAGE_NUM_ROWS,
            index_col=0,
            engine="openpyxl",
        )
        # The index (first column in the spreadsheet) lists something
        # like bidding zones with the first two characters being
        # the country code, so we sum all the columns (installed
        # capacities) across these country codes.
        return df_raw.transpose().groupby(zone_to_country).sum()

    def _load_intercon_from_sheet_header(
        self, year: int, sheet_name: str
    ) -> pandas.DataFrame:
        df_raw = pandas.read_excel(
            self._data_file_intercon(year),
            sheet_name=sheet_name,
            skiprows=Pemmdb2023Loader._INTERCON_SKIP_ROWS,
            nrows=Pemmdb2023Loader._INTERCON_NUM_ROWS,
            index_col=1,
            engine="openpyxl",
        )
        # The index now contains properties of the links (FROM, TO,
        # NET_CAP). Drop the first column which contains labels and
        # transpose to get a tidy table with one row for each link.
        df_long = df_raw.iloc[:, 1:].transpose()
        # Convert capacities to numbers for they were parsed as
        # strings.
        df_long["NET_CAP"] = pandas.to_numeric(df_long["NET_CAP"])
        # Translate zone IDs to country codes.
        df_long[["FROM", "TO"]] = df_long[["FROM", "TO"]].apply(
            lambda columm: columm.apply(zone_to_country)
        )
        # Select links between different countries only.
        df_cross = df_long[df_long["FROM"] != df_long["TO"]]
        return df_cross.groupby(["FROM", "TO"]).sum()

    def _load_intercon_from_sheet_body(
        self, year: int, sheet_name: str
    ) -> pandas.DataFrame:
        df_raw = pandas.read_excel(
            self._data_file_intercon(year),
            sheet_name=sheet_name,
            skiprows=15,
            nrows=8760,
            engine="openpyxl",
        )
        # Calculate a pandas Series of maximum link capacities.
        # Each entry corresponds to one link in on direction.
        max_link_capacities = (
            # Drop irrelevant and empty columns first.
            df_raw.drop(["Date", "Hour"], axis=1)
            .dropna(axis=1, how="all")
            .max()
            .rename(lambda column: column.removeprefix("Hourly values "))
        )
        # Construct indexes for each endpoint of the links.
        index_from = max_link_capacities.index.map(lambda column: column.split("-")[0])
        index_to = max_link_capacities.index.map(lambda column: column.split("-")[1])

        df_links = pandas.DataFrame(
            {
                "FROM": index_from,
                "TO": index_to,
                "NET_CAP": max_link_capacities,
            }
        )
        # Translate zone IDs to country codes.
        df_links[["FROM", "TO"]] = df_links[["FROM", "TO"]].apply(
            lambda columm: columm.apply(zone_to_country)
        )
        # Select links between different countries only.
        df_cross = df_links[df_links["FROM"] != df_links["TO"]]
        return df_cross.groupby(["FROM", "TO"]).sum()

    def _sheet_name(self, year: int):
        return f"TY{year}"

    def get_basic_sources(
        self,
        country: Zone,
        year: int,
        allow_capex_optimization=False,
        profile_overrides: Optional[dict[BasicSourceType, Zone]] = None,
    ) -> dict[BasicSourceType, dict]:
        installed_map = self.get_installed(country, year)
        sources: dict[BasicSourceType, dict] = {}

        for source_type, installed_gw in installed_map.items():
            installed_mw = 1000 * installed_gw
            # Ignore sources below 100 kW.
            if installed_mw < 0.1:
                continue

            sources[source_type] = {
                "capacity_mw": installed_mw,
                "min_capacity_mw": 0 if allow_capex_optimization else installed_mw,
            }

            if profile_overrides and source_type in profile_overrides:
                override_country = profile_overrides[source_type]
                override_installed = self.get_installed(override_country, year)[
                    source_type
                ]
                sources[source_type]["profile_override"] = ProfileOverride(
                    override_country, override_installed, source_type
                )

        return sources

    def get_countries_from_aggregate(
        self,
        region: AggregateRegion,
        year: int,
        overrides: Optional[dict[Zone, dict[BasicSourceType, Zone]]] = None,
        include_reserves=False,
    ) -> dict[Zone, dict[str, Any]]:
        if not overrides:
            overrides = {}

        return {
            part: self.get_country(
                country=part,
                year=year,
                in_aggregate=region,
                profile_overrides=overrides.get(part),
                include_reserves=include_reserves,
            )
            for part in get_aggregated_countries(region)
        }

    def get_country(
        self,
        country: Zone,
        year: int,
        allow_capex_optimization=False,
        in_aggregate: Optional[AggregateRegion] = None,
        profile_overrides: Optional[dict[BasicSourceType, Zone]] = None,
        include_reserves=False,
    ) -> dict[str, Any]:
        result = {
            "basic_sources": self.get_basic_sources(
                country,
                year,
                allow_capex_optimization,
                profile_overrides=profile_overrides,
            ),
            "flexible_sources": self.get_flexible_sources(
                country, year, allow_capex_optimization
            ),
            "installed_gw": self.get_installed(country, year),
            "load_factors": self.get_load_factors(country, year),
            "storage": self.get_storage(country, year, allow_capex_optimization),
        }

        if include_reserves:
            reserves = self.get_reserve_requirements(country, year)
            if reserves:
                result["reserves"] = reserves

        if in_aggregate:
            result["in_aggregate"] = in_aggregate

        return result

    def get_flexible_sources(
        self, country: Zone, year: int, allow_capex_optimization=False
    ) -> dict[FlexibleSourceType, dict]:
        pemmdb_country = map_to_pemmdb_region(country)
        sources: dict[FlexibleSourceType, dict] = {}

        if pemmdb_country not in self._df_sources(year).index:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ not available in PEMMDB dataset"
            )

        for pemmdb_key, (
            source_type,
            template,
        ) in self._FLEXIBLE_SOURCES_MAP.items():
            installed_mw = float(self._df_sources(year).loc[pemmdb_country, pemmdb_key])
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

        if pemmdb_country not in self._df_sources(year).index:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ not available in PEMMDB dataset"
            )

        for pemmdb_key, source_type in self._BASIC_SOURCES_MAP.items():
            installed_mw = float(self._df_sources(year).loc[pemmdb_country, pemmdb_key])
            sources[source_type] = installed_mw / 1000

        return sources

    def get_interconnectors(
        self,
        year: int,
        countries: Optional[Collection[Zone]] = None,
        aggregate_countries: Optional[Collection[AggregateRegion]] = None,
        choke_factor: float = 1.0,
    ) -> InterconnectorsDict:
        df_intercon = self._df_intercon(year)

        countries = {map_to_pemmdb_region(c) for c in countries} if countries else None

        map_from_to: dict[Region, dict[Region, dict]] = defaultdict(dict)
        for (ix_from, ix_to), value_mw in df_intercon.iterrows():
            region_from = Region(ix_from)
            region_to = Region(ix_to)
            if countries and (
                region_from not in countries or region_to not in countries
            ):
                continue
            capacity_mw = value_mw.iloc[0] * choke_factor
            map_from_to[region_from][region_to] = {
                "capacity_mw": capacity_mw,
                "paid_off_capacity_mw": capacity_mw,
            }

        # Rename the PEMMDB region names back to our names.
        def rename_dict(d: dict[Region, Any], pemmdb_name: str, country: Zone):
            if pemmdb_name in d:
                d[country] = d[pemmdb_name]
                del d[pemmdb_name]

        for country, pemmdb_name in PEMMDB_COUNTRY_MAP.items():
            rename_dict(map_from_to, pemmdb_name, country)
            for to_dict in map_from_to.values():
                rename_dict(to_dict, pemmdb_name, country)

        add_distances_type_and_loss_to_interconnectors(map_from_to)

        if aggregate_countries:
            map_from_to = aggregate_interconnectors(map_from_to, aggregate_countries)

        return dict(map_from_to)

    def get_load_factors(self, country: Zone, year: int) -> LoadFactors:
        return {"load_base": 1.0}

    def get_reserve_requirements(
        self, country: Zone, year: int
    ) -> Optional[ReservesRequirements]:
        pemmdb_country = map_to_pemmdb_region(country)

        if (pemmdb_country, year) not in self._df_reserves.index:
            return

        pemmdb_reserves = self._df_reserves.loc[[(pemmdb_country, year)]].iloc[0]

        reserves = ReservesRequirements(
            hydro_derating_mw=pemmdb_reserves[
                "Sum of reserves provided by hydro units (MW)"
            ],
            thermal_derating_mw=pemmdb_reserves[
                "Sum of reserves provided by thermal units (MW)"
            ],
        )

        return reserves

    def get_storage(
        self, country: Zone, year: int, allow_capex_optimization=False
    ) -> dict[StorageType, dict]:
        pemmdb_country = map_to_pemmdb_region(country)
        storages: dict[StorageType, dict] = {}

        df_sources = self._df_sources(year)
        df_storage = self._df_storage(year)
        if pemmdb_country not in df_sources.index:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ not available in PEMMDB dataset"
            )

        sources_series = df_sources.loc[pemmdb_country]
        storage_series = df_storage.loc[pemmdb_country]

        # Load Li-ion batteries parameters.
        batteries = _pemmdb_load_batteries(
            sources_series, storage_series, allow_capex_optimization
        )
        if batteries:
            storages[StorageType.LI] = batteries

        ror = _pemmdb_load_ror_hydro(sources_series)
        if ror:
            storages[StorageType.ROR] = ror

        pondage = _pemmdb_load_pondage_hydro(sources_series, storage_series)
        if pondage:
            storages[StorageType.PONDAGE] = pondage

        pumped = _pemmdb_load_pumped_hydro(sources_series, storage_series)
        if pumped:
            storages |= pumped

        reservoir = _pemmdb_load_reservoir_hydro(sources_series, storage_series)
        if reservoir:
            storages[StorageType.RESERVOIR] = reservoir

        return storages

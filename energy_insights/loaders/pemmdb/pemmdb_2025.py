import re
from functools import cached_property
from pathlib import Path
from typing import Any, Optional, Union, override

import pandas

from ...region import AggregateRegion, Zone
from ...params_library.interconnectors import get_aggregated_countries
from ...sources.basic_source import BasicSourceType
from ...sources.flexible_source import FlexibleSourceType
from ...sources.reserves import ReservesRequirements
from ...sources.storage import StorageType

from .common import map_to_pemmdb_region, make_battery, zone_to_country
from .pemmdb_2024 import Pemmdb2024Loader

# Raw datasets downloaded from the ERAA 2025 stakeholder interactions
# page[1], section "ERAA 2025: Preliminary input data following the
# Call for Evidence".
#
# PEMMDB stands for "Pan-European Market Database". It is maintained by
# the System Adequacy and Market Modelling working group[2] (WG SAMM) at
# ENTSO-E. ERAA stands for "European Resource Adequacy Assessment".
#
# [1]: https://www.entsoe.eu/outlooks/eraa/stakeholder-interactions/
# [2]: https://docstore.entsoe.eu/about-entso-e/system-development/system-adequacy-and-market-modeling/Pages/default.aspx


_PEMMDB_2025_BASIC_SOURCES_MAP: dict[str, BasicSourceType] = {
    "Nuclear": BasicSourceType.NUCLEAR,
    "Solar PV utility non-tracking": BasicSourceType.SOLAR,
    "Solar PV utility tracking": BasicSourceType.SOLAR,
    "Solar PV rooftop residential": BasicSourceType.SOLAR,
    "Solar PV rooftop industrial": BasicSourceType.SOLAR,
    "Wind offshore fixed": BasicSourceType.OFFSHORE,
    "Wind offshore floating": BasicSourceType.OFFSHORE,
    "Wind onshore": BasicSourceType.ONSHORE,
}

_PEMMDB_2025_FLEXIBLE_SOURCES_MAP: dict[str, tuple[FlexibleSourceType, dict]] = {
    "Biofuel": (
        FlexibleSourceType.BIOGAS,
        {"uptime_ratio": 0.8, "overnight_costs_per_kw_eur": 1800},
    ),
    "DSR": (FlexibleSourceType.DSR, {}),
    "Hard coal": (FlexibleSourceType.COAL, {}),
    # NOTE: The pipe denotes variants. It is NOT a regular expression.
    # We do thi because dict keys must be hashable and so a list cannot be used.
    "Heavy oil|Light oil|Shale oil": (FlexibleSourceType.FOSSIL_OIL, {}),
    "Lignite": (FlexibleSourceType.LIGNITE, {}),
    "Natural gas": (FlexibleSourceType.GAS_CCGT, {}),
    "Small biomass": (
        FlexibleSourceType.SOLID_BIOMASS,
        {"uptime_ratio": 0.8, "overnight_costs_per_kw_eur": 1800},
    ),
    "Waste": (FlexibleSourceType.WASTE, {}),
    # TODO: Map Electrolyser and Hydrogen and Hydrogen to something hydrogen-adjacent.
    # TODO: Can we map Geothermal (so far mostly in Italy only) in a useful way?
}


class Pemmdb2025Loader(Pemmdb2024Loader):
    """
    Loader for the preliminary 2025 edition of the Pan-European Market
    Modelling Database (PEMMDB). This dataset is prepared regularly for
    the modelling needs of the European Resource Adequacy Assessment
    (ERAA).
    """

    _EDITION = 2025
    _TARGET_YEARS = (2028, 2030, 2033, 2035)

    _BASIC_SOURCES_MAP = _PEMMDB_2025_BASIC_SOURCES_MAP
    _FLEXIBLE_SOURCES_MAP = _PEMMDB_2025_FLEXIBLE_SOURCES_MAP

    def __init__(self, data_directory: Union[str, Path]) -> None:
        data_directory = Path(data_directory)
        self._data_file_capacities = (
            data_directory / "ERAA2025 GenerationCapacities.csv"
        )
        self._data_file_eva = data_directory / "ERAA_2025_EVA.xlsx"
        self._data_file_hydro = data_directory / "ERAA2025 Hydro.csv"
        self._data_file_reserves = data_directory / "ERAA2025 Reserves.csv"
        self._data_file_batteries = data_directory / "ERAA2025 Batteries.csv"

    def _data_file_intercon(self, year: int) -> Path:
        data_directory = self._data_file_capacities.parent
        return data_directory / f"ERAA2025 NTCs TY{year}.xlsx"

    @cached_property
    def _df_batteries(self) -> pandas.DataFrame:
        """Dataset of battery capacities."""
        grouping = ["COUNTRY", "YEAR"]

        # TODO: What to do with "Non-market batteries" in ERAA 2025?
        # We're summing them into the market for now.
        df_raw = (
            pandas.read_csv(self._data_file_batteries)
            .rename(
                columns={
                    "MAX LOAD CAP (MW)": "CAPACITY_MW",
                    "STORAGE CAPACITY (MWh)": "MAX_ENERGY_MWH",
                    "TARGET_YEAR": "YEAR",
                }
            )
            .query(
                "data_version == 'ERAA 2025 final' and"
                " OP_STAT in ('Available on market',"
                "             'Out of market - for PV/battery dispatch optimization')"
            )
        )
        df_raw["COUNTRY"] = df_raw["MARKET_NODE"].apply(zone_to_country)

        return (
            df_raw[grouping + ["CAPACITY_MW", "MAX_ENERGY_MWH"]].groupby(grouping).sum()
        )

    @cached_property
    def _df_eva(self) -> pandas.DataFrame:
        grouping = ["COUNTRY", "YEAR", "TECHNOLOGY"]

        df_raw = (
            pandas.read_excel(
                self._data_file_eva, engine="openpyxl", sheet_name="Revenue Based"
            )
            .rename(
                columns={
                    "Capacity Change": "CAPACITY_MW",
                    "Technology": "TECHNOLOGY",
                    "Year": "YEAR",
                }
            )
            .query("`Model version` == 'Implementation A'")
        )
        df_raw["COUNTRY"] = df_raw["Node"].apply(zone_to_country)

        def _map_technology(s: str) -> str:
            technology = re.sub(
                r"\s*(CCGT|OCGT|conventional)?\s*(new|old|present)( \d+)?( candidate)?$",
                "",
                s,
            )

            if "dsr" in technology.lower():
                return "DSR"
            if technology == "Gas":
                return "Natural gas"
            return technology

        df_raw["TECHNOLOGY"] = df_raw["TECHNOLOGY"].map(_map_technology)

        return df_raw[grouping + ["CAPACITY_MW"]].groupby(grouping).sum()

    @cached_property
    def _df_hydro(self) -> pandas.DataFrame:
        """Dataset of hydro capacities."""
        grouping = ["COUNTRY", "YEAR", "TECHNOLOGY"]

        df_raw = (
            pandas.read_csv(self._data_file_hydro)
            .rename(
                columns={
                    "Country": "COUNTRY",
                    "MAX PUMPING CAP (MW)": "CAPACITY_MW_CHARGING",
                    "PEMMDB_PLANT_TYPE": "TECHNOLOGY",
                    "Storage Capacity [TWh]": "MAX_ENERGY_TWH",
                    "TARGET_YEAR": "YEAR",
                }
            )
            .query("data_version == 'ERAA 2025 final'")
        )
        # NOTE: The fixed lower bound is a workaround for PEMMDB 2025,
        # which lists storage capacities in TWh but only down to two
        # decimal places. This causes (mainly) pumped hydro to disappear
        # from several countries, including Czechia.
        df_raw["MAX_ENERGY_MWH"] = 1e6 * df_raw["MAX_ENERGY_TWH"].clip(lower=0.004)

        df_summed = (
            df_raw[grouping + ["CAPACITY_MW_CHARGING", "MAX_ENERGY_MWH"]]
            .groupby(grouping)
            .sum()
        )

        # Include installed capacities (for generation/dispatch) from
        # the "generation capacities" data sheet.
        return df_summed.join(self._df_sources, how="inner")

    @cached_property
    def _df_reserves(self) -> pandas.DataFrame:
        """Dataset of reserve capacity requirements."""
        grouping = ["COUNTRY", "YEAR", "CATEGORY"]

        df_raw = (
            pandas.read_csv(self._data_file_reserves)
            .rename(columns={"Value": "CAPACITY_MW", "Category": "CATEGORY"})
            .query("data_version == 'ERAA 2025 final'")
        )
        df_raw["COUNTRY"] = df_raw["MARKET_NODE"].apply(zone_to_country)

        return df_raw[grouping + ["CAPACITY_MW"]].groupby(grouping).sum()

    @cached_property
    def _df_sources(self) -> pandas.DataFrame:
        """Dataset of installed capacities of generation technologies."""
        grouping = ["COUNTRY", "YEAR", "TECHNOLOGY"]

        # TODO: What to do with solar thermal?
        #   - "Solar thermal with storage"
        #   - "Solar thermal without storage"
        # TODO: Load Operational_Status == "Inelastic supply / fixed profile" as well?
        df_raw = (
            pandas.read_csv(self._data_file_capacities)
            .rename(
                columns={
                    "Market_Node": "MARKET_NODE",
                    "Target year": "YEAR",
                    "Technology": "TECHNOLOGY",
                    "Value": "CAPACITY_MW",
                }
            )
            .query(
                "data_version == 'ERAA 2025 final' and"
                " (Operational_Status == 'Available on market' or"
                "  Operational_Status == 'Out of market – for PV/battery dispatch optimization')"
            )
        )
        df_raw["COUNTRY"] = df_raw["MARKET_NODE"].apply(zone_to_country)
        df_raw["CAPACITY_MW"] = df_raw["CAPACITY_MW"].astype(float)

        return df_raw[grouping + ["CAPACITY_MW"]].groupby(grouping).sum()

    @override
    def get_countries_from_aggregate(
        self,
        region: AggregateRegion,
        year: int,
        overrides: Optional[dict[Zone, dict[BasicSourceType, Zone]]] = None,
        include_reserves=False,
        post_eva=False,
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
                post_eva=post_eva,
            )
            for part in get_aggregated_countries(region)
        }

    @override
    def get_country(
        self,
        country: Zone,
        year: int,
        allow_capex_optimization=False,
        in_aggregate: Optional[AggregateRegion] = None,
        profile_overrides: Optional[dict[BasicSourceType, Zone]] = None,
        include_reserves=False,
        post_eva=False,
    ) -> dict[str, Any]:
        result = {
            "basic_sources": self.get_basic_sources(
                country,
                year,
                allow_capex_optimization,
                profile_overrides=profile_overrides,
            ),
            "flexible_sources": self.get_flexible_sources(
                country, year, allow_capex_optimization, post_eva=post_eva
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

    @override
    def get_flexible_sources(
        self, country: Zone, year: int, allow_capex_optimization=False, post_eva=False
    ) -> dict[FlexibleSourceType, dict]:
        pemmdb_country = map_to_pemmdb_region(country)
        sources: dict[FlexibleSourceType, dict] = {}

        try:
            df_sources = self._df_sources.loc[(pemmdb_country, year)]
        except KeyError:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ with TY {year} not available in PEMMDB dataset"
            )

        # Subtract (or add) capacities retired (or added) in the economic
        # viability assessment (EVA).
        if post_eva and (pemmdb_country, year) in self._df_eva.index:
            df_sources = df_sources.add(
                self._df_eva.loc[(pemmdb_country, year)], fill_value=0.0
            )

        for pemmdb_key, (
            source_type,
            template,
        ) in self._FLEXIBLE_SOURCES_MAP.items():
            pemmdb_keys = df_sources.index.intersection(pemmdb_key.split("|"))
            if pemmdb_keys.empty:
                continue
            installed_mw = float(df_sources.loc[pemmdb_keys, "CAPACITY_MW"].sum())
            assert installed_mw >= 0.0
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

        try:
            df_sources = self._df_sources.loc[(pemmdb_country, year)]
        except KeyError:
            raise ValueError(
                f"Country ‘{pemmdb_country}’ with TY {year} not available in PEMMDB dataset"
            )

        df_sources = df_sources.reset_index("TECHNOLOGY")
        df_sources["TECHNOLOGY"] = df_sources["TECHNOLOGY"].map(self._BASIC_SOURCES_MAP)
        df_sources = df_sources.groupby("TECHNOLOGY", sort=False).sum()

        for source_type, installed_mw in df_sources.iterrows():
            sources[source_type] = installed_mw.iloc[0] / 1000

        return sources

    def get_reserve_requirements(
        self, country: Zone, year: int
    ) -> Optional[ReservesRequirements]:
        pemmdb_country = map_to_pemmdb_region(country)

        try:
            pemmdb_reserves = self._df_reserves.loc[(pemmdb_country, year)][
                "CAPACITY_MW"
            ]
        except KeyError:
            return

        required_fcr = pemmdb_reserves.get("FCR", 0.0)
        required_frr = pemmdb_reserves.get("FRR", 0.0)

        if required_fcr > 0.0 or required_frr > 0.0:
            return ReservesRequirements(
                fcr=required_fcr,
                frr=required_frr,
            )

    def get_storage(
        self, country: Zone, year: int, allow_capex_optimization=False
    ) -> dict[StorageType, dict]:
        pemmdb_country = map_to_pemmdb_region(country)
        storages: dict[StorageType, dict] = {}

        try:
            row = self._df_batteries.loc[(pemmdb_country, year)]
            capacity_mw = row["CAPACITY_MW"]
            max_energy_mwh = row["MAX_ENERGY_MWH"]

            batteries = make_battery(
                capacity_mw, capacity_mw, max_energy_mwh, allow_capex_optimization
            )
            if batteries:
                storages[StorageType.LI] = batteries
        except KeyError:
            # Skip unavailable battery capacities silenlty.
            pass

        storages |= self._load_hydro(pemmdb_country, year)

        return storages

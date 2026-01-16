"""
Loads hourly/15m data from ENTSO-E and a given country and year.

This code is a slightly modified version of
https://github.com/electricitymaps/electricitymaps-contrib/blob/ac2a3c41a41f779b79fe61d5a2e489bdb2d0cb3d/parsers/ENTSOE.py
licensed under GNU-AGPLv3.
"""

import re
from collections import defaultdict
from datetime import datetime
from functools import cached_property
from pathlib import Path
from random import shuffle
from typing import Any, Optional, Tuple, Union

import arrow
import pandas as pd
from bs4 import BeautifulSoup
from requests import Response, Session

from .entsoe_validator import validate_entsoe
from .grid_plot_utils import Keys
from .logging import get_logger
from .region import *

logger = get_logger(__name__)

ENTSOE_ENDPOINT = "https://web-api.tp.entsoe.eu/api"
ENTSOE_PARAMETER_DESC = {
    "B01": Keys.BIOMASS,
    "B02": "Fossil Brown coal/Lignite",
    "B03": "Fossil Coal-derived gas",
    "B04": "Fossil Gas",
    "B05": "Fossil Hard coal",
    "B06": "Fossil Oil",
    "B07": "Fossil Oil shale",
    "B08": "Fossil Peat",
    "B09": "Geothermal",
    "B10": "Hydro Pumped Storage",
    "B11": "Hydro Run-of-river and poundage",
    "B12": "Hydro Water Reservoir",
    "B13": "Marine",
    "B14": Keys.NUCLEAR,
    "B15": "Other renewable",
    "B16": Keys.SOLAR,
    "B17": "Waste",
    "B18": "Wind Offshore",
    "B19": "Wind Onshore",
    "B20": Keys.OTHER,
}

# Hydro pumped storage consumption
ENTSOE_PARAMETER_GROUPS = {
    "production": {
        Keys.BIOMASS: ["B01", "B15"],
        Keys.HYDRO: ["B11", "B12"],
        Keys.NUCLEAR: ["B14"],
        Keys.SOLAR: ["B16"],
        Keys.WIND_OFFSHORE: ["B18"],
        Keys.WIND_ONSHORE: ["B19"],
        # Other categories not used by the model but useful to keep.
        Keys.COAL: ["B02", "B05", "B07", "B08"],
        Keys.GAS: ["B03", "B04"],
        Keys.GEOTHERMAL: ["B09"],
        Keys.OIL: ["B06"],
        Keys.OTHER: ["B13", "B17", "B20"],
    },
    "storage": {Keys.HYDRO_PUMPED_STORAGE: ["B10"]},
}

# Define all ENTSOE zone_key <-> domain mapping
# see https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
ENTSOE_DOMAIN_MAPPINGS: dict[Zone, str] = {
    ALBANIA: "10YAL-KESH-----5",
    AUSTRIA: "10YAT-APG------L",
    AZERBAIJAN: "10Y1001A1001B05V",
    BOSNIA_HERZEGOVINA: "10YBA-JPCC-----D",
    BELARUS: "10Y1001A1001A51S",
    BELGIUM: "10YBE----------2",
    BULGARIA: "10YCA-BULGARIA-R",
    CROATIA: "10YHR-HEP------M",
    CYPRUS: "10YCY-1001A0003J",
    CZECHIA: "10YCZ-CEPS-----N",
    DENMARK: "10Y1001A1001A65H",
    DENMARK_1: "10YDK-1--------W",
    DENMARK_2: "10YDK-2--------M",
    ESTONIA: "10Y1001A1001A39I",
    FINLAND: "10YFI-1--------U",
    FRANCE: "10YFR-RTE------C",
    GERMANY: "10Y1001A1001A83F",
    GERMANY_LUXEMBOURG: "10Y1001A1001A82H",
    GREAT_BRITAIN: "10YGB----------A",
    GREAT_BRITAIN_NORTHERN_IRELAND: "10Y1001A1001A016",
    GEORGIA: "10Y1001A1001B012",
    GREECE: "10YGR-HTSO-----Y",
    HUNGARY: "10YHU-MAVIR----U",
    IRELAND: "10YIE-1001A00010",
    IRELAND_WHOLE: "10Y1001A1001A59C",
    ITALY: "10YIT-GRTN-----B",
    ITALY_CENTRAL_NORTH: "10Y1001A1001A70O",
    ITALY_CENTRAL_SOUTH: "10Y1001A1001A71M",
    ITALY_NORTH: "10Y1001A1001A73I",
    ITALY_SARDINIA: "10Y1001A1001A74G",
    ITALY_SICILY: "10Y1001A1001A75E",
    ITALY_SOUTH: "10Y1001A1001A788",
    KOSOVO: "10Y1001C--00100H",
    LATVIA: "10YLV-1001A00074",
    LITHUANIA: "10YLT-1001A0008Q",
    LUXEMBOURG: "10YLU-CEGEDEL-NQ",
    MOLDOVA: "10Y1001A1001A990",
    MONTENEGRO: "10YCS-CG-TSO---S",
    NORTH_MACEDONIA: "10YMK-MEPSO----8",
    MALTA: "10Y1001A1001A93C",
    NETHERLANDS: "10YNL----------L",
    NORWAY: "10YNO-0--------C",
    NORWAY_1: "10YNO-1--------2",
    NORWAY_2: "10YNO-2--------T",
    NORWAY_3: "10YNO-3--------J",
    NORWAY_4: "10YNO-4--------9",
    NORWAY_5: "10Y1001A1001A48H",
    POLAND: "10YPL-AREA-----S",
    PORTUGAL: "10YPT-REN------W",
    ROMANIA: "10YRO-TEL------P",
    RUSSIA: "10Y1001A1001A49F",
    RUSSIA_KALININGRAD: "10Y1001A1001A50U",
    SPAIN: "10YES-REE------0",
    SERBIA: "10YCS-SERBIATSOV",
    SWEDEN: "10YSE-1--------K",
    SWEDEN_1: "10Y1001A1001A44P",
    SWEDEN_2: "10Y1001A1001A45N",
    SWEDEN_3: "10Y1001A1001A46L",
    SWEDEN_4: "10Y1001A1001A47J",
    SLOVENIA: "10YSI-ELES-----O",
    SLOVAKIA: "10YSK-SEPS-----K",
    SWITZERLAND: "10YCH-SWISSGRIDZ",
    TURKEY: "10YTR-TEIAS----W",
    UKRAINE: "10YUA-WEPS-----0",
}

# Some zone_keys are part of bidding zone domains for price data
ENTSOE_PRICE_DOMAIN_MAPPINGS: dict[Zone, str] = {
    **ENTSOE_DOMAIN_MAPPINGS,  # Note: This has to be first so the domains are overwritten.
    GERMANY: ENTSOE_DOMAIN_MAPPINGS[GERMANY_LUXEMBOURG],
    LUXEMBOURG: ENTSOE_DOMAIN_MAPPINGS[GERMANY_LUXEMBOURG],
    IRELAND: ENTSOE_DOMAIN_MAPPINGS[IRELAND_WHOLE],
}

VALIDATIONS: dict[Zone, dict[str, Any]] = {
    # This is a list of criteria to ensure validity of data,
    # used in validate_production()
    # Note that "required" means data is present in ENTSOE.
    # It will still work if data is present but 0.
    # "expected_range" and "floor" only count production and storage
    # - not exchanges!
    AUSTRIA: {
        "required": [Keys.HYDRO],
    },
    BOSNIA_HERZEGOVINA: {
        "required": [Keys.COAL, Keys.HYDRO, Keys.WIND_ONSHORE],
        "expected_range": (500, 6500),
    },
    BELGIUM: {
        "required": [Keys.GAS, Keys.NUCLEAR],
        "expected_range": (3000, 25000),
    },
    BULGARIA: {
        "required": [Keys.COAL, Keys.NUCLEAR, Keys.HYDRO],
        "expected_range": (2000, 20000),
    },
    CROATIA: {
        "required": [
            Keys.COAL,
            Keys.GAS,
            Keys.WIND_ONSHORE,
            Keys.BIOMASS,
            Keys.OIL,
            Keys.SOLAR,
        ],
    },
    CZECHIA: {
        # usual load is in 7-12 GW range
        "required": [Keys.COAL, Keys.NUCLEAR],
        "expected_range": (3000, 25000),
    },
    ESTONIA: {
        "required": [Keys.COAL],
    },
    FINLAND: {
        "required": [Keys.COAL, Keys.NUCLEAR, Keys.HYDRO, Keys.BIOMASS],
        "expected_range": (2000, 20000),
    },
    GERMANY: {
        # Germany sometimes has problems with categories of generation missing from ENTSOE.
        # Normally there is constant production of a few GW from hydro and biomass
        # and when those are missing this can indicate that others are missing as well.
        # We have also never seen unknown being 0.
        # Usual load is in 30 to 80 GW range.
        "required": [
            Keys.COAL,
            Keys.GAS,
            Keys.NUCLEAR,
            Keys.WIND_ONSHORE,
            Keys.BIOMASS,
            Keys.HYDRO,
            Keys.OTHER,
            Keys.SOLAR,
        ],
        "expected_range": (20000, 100000),
    },
    GREAT_BRITAIN: {
        # usual load is in 15 to 50 GW range
        "required": [Keys.COAL, Keys.GAS, Keys.NUCLEAR],
        "expected_range": (10000, 80000),
    },
    GREECE: {
        "required": [Keys.COAL, Keys.GAS],
        "expected_range": (2000, 20000),
    },
    HUNGARY: {
        "required": [Keys.COAL, Keys.NUCLEAR],
    },
    IRELAND: {
        "required": [Keys.COAL],
        "expected_range": (1000, 15000),
    },
    ITALY: {
        "required": [Keys.COAL],
        "expected_range": (5000, 50000),
    },
    POLAND: {
        # usual load is in 10-20 GW range and coal is always present
        "required": [Keys.COAL],
        "expected_range": (5000, 35000),
    },
    PORTUGAL: {
        "required": [Keys.COAL, Keys.GAS],
        "expected_range": (1000, 20000),
    },
    ROMANIA: {
        "required": [Keys.COAL, Keys.NUCLEAR, Keys.HYDRO],
        "expected_range": (2000, 25000),
    },
    SERBIA: {
        "required": [Keys.COAL],
    },
    SLOVAKIA: {"required": [Keys.NUCLEAR]},
    SLOVENIA: {
        # own total generation capacity is around 4 GW
        "required": [Keys.NUCLEAR],
        "expected_range": (140, 5000),
    },
    SPAIN: {
        "required": [Keys.COAL, Keys.NUCLEAR],
        "expected_range": (10000, 80000),
    },
    SWEDEN: {
        "required": [Keys.HYDRO, Keys.NUCLEAR, Keys.WIND_ONSHORE, Keys.OTHER],
    },
    SWEDEN_1: {
        "required": [Keys.HYDRO, Keys.WIND_ONSHORE, Keys.OTHER, Keys.SOLAR],
    },
    SWEDEN_2: {
        "required": [Keys.GAS, Keys.HYDRO, Keys.WIND_ONSHORE, Keys.OTHER, Keys.SOLAR],
    },
    SWEDEN_3: {
        "required": [
            Keys.GAS,
            Keys.HYDRO,
            Keys.NUCLEAR,
            Keys.WIND_ONSHORE,
            Keys.OTHER,
            Keys.SOLAR,
        ],
    },
    SWEDEN_4: {
        "required": [Keys.GAS, Keys.HYDRO, Keys.WIND_ONSHORE, Keys.OTHER, Keys.SOLAR],
    },
    SWITZERLAND: {
        "required": [Keys.HYDRO, Keys.NUCLEAR],
        "expected_range": (2000, 25000),
    },
}


def _datetime_from_position(
    start: arrow.Arrow, position: int, resolution: str
) -> datetime:
    """Finds time granularity of data."""

    m = re.search(r"PT(\d+)([M])", resolution)
    if m is not None:
        digits = int(m.group(1))
        scale = m.group(2)
        if scale == "M":
            return start.shift(minutes=(position - 1) * digits).datetime
    raise NotImplementedError("Could not recognize resolution %s" % resolution)


def _serialize_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class EntsoeDownloader:
    def __init__(
        self,
        data_path: str,
    ) -> None:
        self.data_path = data_path

    def _get_path(self, zone_key: Zone, year: int) -> str:
        """
        Returns the path for data file to be fetched for provided `zone_key` and `year`.
        """
        return f"{self.data_path}/entsoe/local/{zone_key}-{year}.csv"

    def _get_tokens_path(self) -> str:
        """
        Returns the path for file with tokens for communicating with the ENTSOE API.
        """
        return f"{self.data_path}/entsoe/local/tokens.txt"

    @cached_property
    def _tokens(self) -> list[str]:
        """
        Returns the list of string tokens for communicating with the ENTSOE API.
        Raises an exception if no API token is found.
        """
        tokens_file = Path(self._get_tokens_path())
        if not tokens_file.exists():
            tokens_help_url = "https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html#_authentication_and_authorisation"
            raise Exception(
                f"Tokens for ENTSOE missing. Get a token as documented in {tokens_help_url} and"
                f"store it into file {tokens_file} as 'ENTSOE_TOKENS = [\"YOUR-TOKEN\"]'."
            )
        tokens = tokens_file.read_text().split("\n")

        # Due to rate limiting, we need to spread our requests across different tokens
        # Shuffle the tokens so that we don't always use the same one first.
        shuffle(tokens)

        return tokens

    def _query_entsoe(
        self,
        session: Session,
        params: dict[str, str],
        year: int,
    ) -> str:
        """
        Makes a standard query to the ENTSOE API with a modifiable set of parameters to fetch data
        for a given year. Retries as many times as there are tokens (to work well with rate
        limiting).

        Arguments:
            session: A session to use for the request.
            params: Params to be sent as part of the request.
            year: The year to fetch data for.

        Returns: the server response XML as a string.

        Raises an exception if the request fails.
        """
        # YYYYMMDDHH00
        params["periodStart"] = f"{year}01010000"
        params["periodEnd"] = f"{year+1}01010000"

        # Try each token until we get a valid response
        last_response_if_all_fail = None
        for token in self._tokens:
            params["securityToken"] = token
            response: Response = session.get(ENTSOE_ENDPOINT, params=params)
            if response.ok:
                return response.text
            else:
                last_response_if_all_fail = response

        # If we get here, all tokens failed to fetch valid data
        # and we will check the last response for a error message.
        exception_message = "An unknown error occured while querying ENTSOE."
        if last_response_if_all_fail is not None:
            exception_message = last_response_if_all_fail.text
        raise Exception(f"Error in fetching data from ENTSOE: {exception_message}")

    def _query_load(
        self,
        domain: str,
        session: Session,
        year: int,
    ) -> Optional[str]:
        """
        Makes a query to the ENTSOE API to fetch historical load profiles for a given API `domain` and given `year`. The query is part of the provided request `session`. Returns response XML
        as a string.
        """
        params = {
            "documentType": "A65",
            "processType": "A16",  # Realised.
            "outBiddingZone_Domain": domain,
        }
        return self._query_entsoe(session, params, year)

    def _query_production(
        self,
        domain: str,
        session: Session,
        year: int,
    ) -> Optional[str]:
        """
        Makes a query to the ENTSOE API to fetch historical production profiles for a given API
        `domain` and given `year`. The query is part of the provided request `session`. Returns
        response XML as a string.
        """
        params = {
            "documentType": "A75",
            "processType": "A16",  # Realised.
            "in_Domain": domain,
        }
        return self._query_entsoe(session, params, year)

    def _query_prices(
        self,
        domain: str,
        session: Session,
        year: int,
    ) -> Optional[str]:
        """
        Makes a query to the ENTSOE API to fetch historical cost profiles for a given API `domain`
        and given `year`. The query is part of the provided request `session`. Returns response XML
        as a string.
        """
        params = {
            "documentType": "A44",
            "in_Domain": domain,
            "out_Domain": domain,
        }
        return self._query_entsoe(session, params, year)

    def _parse_load(
        self,
        xml_text: str,
    ) -> Optional[list[Tuple[datetime, float]]]:
        """
        Parses response XML text for a load query into a list of data points.

        Arguments:
            xml_text: The response XML as a plain string.

        Returns: list of data points where each consists of a datetime and a load in MW or None if
            provided xml_text is empty.
        """
        if not xml_text:
            return None
        soup = BeautifulSoup(xml_text, "xml")

        points = []
        # Currently, the query returns only one TimeSeries but there is no guarantee that the data
        # does not get broken up to multiple (non-overlapping) series as in the case of price data.
        for timeseries in soup.find_all("TimeSeries"):
            if not len(timeseries.find_all("outBiddingZone_Domain.mRID")):
                continue

            for period in timeseries.find_all("Period"):
                resolution = str(period.find("resolution").contents[0])
                datetime_start = arrow.get(period.find("start").contents[0])

                for entry in period.find_all("Point"):
                    position = int(entry.find("position").contents[0])
                    value = float(entry.find("quantity").contents[0])
                    datetime = _datetime_from_position(
                        datetime_start, position, resolution
                    )
                    points.append((datetime, value))

        return points

    def _parse_production(
        self,
        xml_text,
    ) -> Optional[dict[str, dict[str, Any]]]:
        """
        Parses response XML text for a production query into a dict of data points.

        Arguments:
            xml_text: The response XML as a plain string.

        Returns: dict of data points, indexed by a string representation of its datetime or None if
            provided xml_text is empty. Each data point itself is a dict of production floats (in
            MW), indexed by ENTSOE strings denoting production categories. See values of
            ENTSOE_PARAMETER_GROUPS for such category strings.
        """
        if not xml_text:
            return None
        soup = BeautifulSoup(xml_text, "xml")

        # Each production type is stored in a separate timeseries that overlap (time-wise).
        # Combine the data into one structure per each time point. Thus, store all data in a dict,
        # with serialized dates as keys.
        points: dict[str, dict[str, Any]] = {}
        for timeseries in soup.find_all("TimeSeries"):
            is_production = timeseries.find("inBiddingZone_Domain.mRID") is not None
            psr_type = str(timeseries.find("MktPSRType").find("psrType").contents[0])

            for period in timeseries.find_all("Period"):
                resolution = str(period.find("resolution").contents[0])
                datetime_start = arrow.get(period.find("start").contents[0])

                for entry in period.find_all("Point"):
                    position = int(entry.find("position").contents[0])
                    quantity = float(entry.find("quantity").contents[0])
                    datetime = _datetime_from_position(
                        datetime_start, position, resolution
                    )
                    dt_key = _serialize_date(datetime)

                    if dt_key not in points:
                        points[dt_key] = defaultdict(lambda: 0)

                    if is_production:
                        points[dt_key][psr_type] += quantity
                    else:
                        # For generator sources, this subtracts self-consumption (i.e. providing net
                        # production). For storage, this is charging.
                        points[dt_key][psr_type] -= quantity

        return points

    def _parse_prices(
        self,
        xml_text: str,
    ) -> Optional[list[Tuple[datetime, float, str]]]:
        """
        Parses response XML text for a price query into a list of data points.

        Arguments:
            xml_text: The response XML as a plain string.

        Returns: list of data points (where each consists of a datetime, a float price, and a string
            currency) or None if provided xml_text is empty.
        """
        if not xml_text:
            return None
        soup = BeautifulSoup(xml_text, "xml")
        points = []
        # There is a timeseries for each day of data (unlike for load where all data is in one
        # TimeSeries).
        for timeseries in soup.find_all("TimeSeries"):
            currency = str(timeseries.find_all("currency_Unit.name")[0].contents[0])
            resolution = str(timeseries.find_all("resolution")[0].contents[0])
            datetime_start: arrow.Arrow = arrow.get(
                timeseries.find_all("start")[0].contents[0]
            )
            for entry in timeseries.find_all("Point"):
                position = int(entry.find_all("position")[0].contents[0])
                datetime = _datetime_from_position(datetime_start, position, resolution)
                price = float(entry.find_all("price.amount")[0].contents[0])
                points.append((datetime, price, currency))

        return points

    def _validate_production(
        self, zone_key: Zone, datapoint: dict[str, Any]
    ) -> Union[dict[str, Any], bool, None]:
        """
        Checks a production data point against built-in country-specific expectations.

        Production data can sometimes be available but clearly wrong. The most common occurrence is
        when the production total is very low and main generation types are missing. In reality a
        country's electrical grid could not function in this scenario.

        Arguments:
            zone_key: The zone for which to take the built-in grid expectations.
            datapoint: The data point to check. For the expected format, see `validate_entsoe()`.

        Returns: True iff the provided data point is valid.
        """

        validation_criteria = VALIDATIONS.get(zone_key, {})

        if validation_criteria:
            return validate_entsoe(zone_key, datapoint, **validation_criteria)

        return True

    def _fetch_load(
        self,
        zone_key: Zone,
        year: int,
        session: Session,
    ) -> pd.DataFrame:
        """Gets load for a specified `zone_key` and `year`, as part of the provided `session`."""
        domain = ENTSOE_DOMAIN_MAPPINGS[zone_key]
        points = None
        raw_consumption = self._query_load(domain, session, year)
        if raw_consumption is None:
            raise Exception(f"No load data found for {zone_key}")
        points = self._parse_load(raw_consumption)
        if not points:
            raise Exception(f"Parsing load data failed for {zone_key}")
        df = pd.DataFrame(
            [
                {
                    Keys.DATE: _serialize_date(datetime),
                    Keys.LOAD: quantity,
                }
                for datetime, quantity in points
            ]
        )
        df.set_index(Keys.DATE, inplace=True)
        return df

    def _fetch_production(
        self,
        zone_key: Zone,
        year: int,
        session: Session,
    ) -> pd.DataFrame:
        """
        Gets production values for all production types for the specified zone_key and year.
        Removes any values that are invalid (as specified by built-in country-specific
        expectations).
        """
        domain = ENTSOE_DOMAIN_MAPPINGS[zone_key]

        production = self._query_production(domain, session, year)
        points = self._parse_production(production)
        if not points:
            raise Exception(f"No production data found for {zone_key}")

        data = []
        for dt_key, production in points.items():
            production_types = {"production": {}, "storage": {}}
            for key in production_types.keys():
                parameter_groups = ENTSOE_PARAMETER_GROUPS[key]
                multiplier = -1 if key == "storage" else 1

                for fuel, groups in parameter_groups.items():
                    has_value = any([production.get(grp) is not None for grp in groups])
                    if has_value:
                        value = sum([production.get(grp, 0) for grp in groups])
                        value *= multiplier
                        if key == "production" and -50 < value < 0:
                            # Set small negative values to 0
                            # FIXME: Issue a log message once a logger is setup.
                            logger.warning(
                                f"Small negative value ({value}) in {fuel} production rounded to 0"
                            )
                            value = 0
                    else:
                        value = None

                    production_types[key][fuel] = value

            data.append(
                {
                    "datetime": dt_key,
                    **production_types,
                }
            )

        def flatten_datapoint(datapoint: dict) -> dict:
            return {
                Keys.DATE: datapoint["datetime"],
                **datapoint["production"],
                **datapoint["storage"],
            }

        result = list(
            map(
                flatten_datapoint,
                filter(lambda x: self._validate_production(zone_key, x), data),
            )
        )
        df = pd.DataFrame(result)
        df.set_index(Keys.DATE, inplace=True)
        return df

    def _fetch_prices(
        self,
        zone_key: Zone,
        year: int,
        session: Session,
    ) -> Optional[pd.DataFrame]:
        """
        Gets day-ahead prices for the specified `zone_key` and `year`. As the data does not have
        to be present in the API, the result is optional.
        """
        domain = ENTSOE_PRICE_DOMAIN_MAPPINGS[zone_key]

        raw_price_data = self._query_prices(domain, session, year)
        if raw_price_data is None:
            raise Exception(f"No price data found for {zone_key}")
        points = self._parse_prices(raw_price_data)
        if not points:
            # FIXME: Issue a log message once a logger is setup.
            logger.warning(
                f"No price values found for {zone_key}, maybe the country is split into multiple market zones?"
            )
            return None
        df = pd.DataFrame(
            [
                {
                    Keys.DATE: _serialize_date(datetime),
                    Keys.PRICE: price,
                    Keys.PRICE_CURRENCY: currency,
                }
                for datetime, price, currency in points
            ]
        )
        df.set_index(Keys.DATE, inplace=True)
        return df

    def fetch(self, zone_key: Zone, year: int) -> None:
        """
        Fetches the data frame for given zone and year and stores it into a CSV file.

        Arguments:
            zone_key: Zone to fetch data for.
            year: Year to fetch hourly/15m data for.
        """
        logger.info(f"Fetching historical data for {zone_key} for year {year}...")
        session = Session()
        production_df = self._fetch_production(zone_key, year, session)
        load_df = self._fetch_load(zone_key, year, session)
        prices_df = self._fetch_prices(zone_key, year, session)
        df = production_df.join(
            load_df if prices_df is None else [load_df, prices_df],
            how="outer",
        ).sort_values(by="Date")
        df.to_csv(self._get_path(zone_key, year))
        logger.info("Done fetching historical data")

"""
Provides a class for regions (and countries in entsoe data).
"""

from typing import Any, Literal, Union

try:
    from pydantic_core import CoreSchema, core_schema
    from pydantic import GetCoreSchemaHandler

    _PYDANTIC_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    # Skip missing Pydantic dependency silently.
    _PYDANTIC_AVAILABLE = False


Region = str
"""
Abstract class for a region for parts of code that does not care about
its semantics.

It is internally a string to allow easy manipulations and type casting.
TODO: potentially avoid string manipulations and convert it to enums.
"""


class Zone(Region):
    """
    Zone is a region for which we have hourly data. Each Zone exists in
    ENTSO-E Transparency Platform (or other entity from which we source
    data). Technically, it is either a bidding zone or a control area or
    a country. For the time being, the exact differentiation between
    those concepts is not needed.
    """

    if _PYDANTIC_AVAILABLE:

        @classmethod
        def __get_pydantic_core_schema__(
            cls, source_type: Any, handler: GetCoreSchemaHandler
        ) -> CoreSchema:
            return core_schema.no_info_after_validator_function(cls, handler(str))


class AggregateRegion(Region):
    """
    AggregateRegion is an aggregate of multiple atomic Zones.
    """


AUSTRIA = Zone("AT")
BELGIUM = Zone("BE")
BULGARIA = Zone("BG")
CROATIA = Zone("HR")
CYPRUS = Zone("CY")
CZECHIA = Zone("CZ")
DENMARK = Zone("DK")
ESTONIA = Zone("EE")
FINLAND = Zone("FI")
FRANCE = Zone("FR")
GERMANY = Zone("DE")
GREECE = Zone("GR")
HUNGARY = Zone("HU")
ITALY = Zone("IT")
IRELAND = Zone("IE")
LATVIA = Zone("LV")
LITHUANIA = Zone("LT")
LUXEMBOURG = Zone("LU")
MALTA = Zone("MT")
NETHERLANDS = Zone("NL")
POLAND = Zone("PL")
PORTUGAL = Zone("PT")
ROMANIA = Zone("RO")
SLOVAKIA = Zone("SK")
SLOVENIA = Zone("SI")
SPAIN = Zone("ES")
SWEDEN = Zone("SE")

# Subzones of countries
DENMARK_1 = Zone("DK-DK1")
DENMARK_2 = Zone("DK-DK2")
ITALY_NORTH = Zone("IT-NO")
ITALY_CENTRAL_NORTH = Zone("IT-CNO")
ITALY_CENTRAL_SOUTH = Zone("IT-CSO")
ITALY_SOUTH = Zone("IT-SO")
ITALY_SICILY = Zone("IT-SIC")
ITALY_SARDINIA = Zone("IT-SAR")
NORWAY_1 = Zone("NO-NO1")
NORWAY_2 = Zone("NO-NO2")
NORWAY_3 = Zone("NO-NO3")
NORWAY_4 = Zone("NO-NO4")
NORWAY_5 = Zone("NO-NO5")
SWEDEN_1 = Zone("SE-SE1")
SWEDEN_2 = Zone("SE-SE2")
SWEDEN_3 = Zone("SE-SE3")
SWEDEN_4 = Zone("SE-SE4")

# Superzones
GERMANY_LUXEMBOURG = Zone("DE-LU")
IRELAND_WHOLE = Zone("IE(SEM)")

# Schengen non-EU countries
GREAT_BRITAIN = Zone("GB")
GREAT_BRITAIN_NORTHERN_IRELAND = Zone("GB-NIR")
NORWAY = Zone("NO")
SWITZERLAND = Zone("CH")

ALBANIA = Zone("AL")
AZERBAIJAN = Zone("AZ")
BELARUS = Zone("BY")
BOSNIA_HERZEGOVINA = Zone("BA")
GEORGIA = Zone("GE")
MOLDOVA = Zone("MD")
MONTENEGRO = Zone("ME")
NORTH_MACEDONIA = Zone("MK")
KOSOVO = Zone("XK")
RUSSIA = Zone("RU")
RUSSIA_KALININGRAD = Zone("RU-KGD")
SERBIA = Zone("RS")
TURKEY = Zone("TR")
UKRAINE = Zone("UA")

# Our own aggregate regions
EU27 = AggregateRegion("EU27")
# Coarse aggregates
NORDICS = AggregateRegion("Nord")
WEST = AggregateRegion("West")
SOUTH = AggregateRegion("South")
BALKANS = AggregateRegion("Balk")
# Midfine aggregates (+ BRITISH_ISLES and IBERIA)
BALTICS = AggregateRegion("Balt")
EAST_BALKAN = AggregateRegion("E_Ba")
SOUTH_CENTRAL_BALKAN = AggregateRegion("SC_Ba")
SLOVENIA_CROATIA_HUNGARY = AggregateRegion("SI_HR_HU")
FRANCE_SWITZERLAND = AggregateRegion("FrCh")
# Fine aggregates
ESTONIA_LATVIA = AggregateRegion("EstLat")
BRITISH_ISLES = AggregateRegion("Brit")
BENELUX = AggregateRegion("Bnl")
BELUX = AggregateRegion("Blx")
IBERIA = AggregateRegion("Iber")
WEST_BALKAN = AggregateRegion("W_Ba")
CENTRAL_BALKAN = AggregateRegion("C_Ba")

GridAggregationLevel = Union[
    Literal["none"], Literal["fine"], Literal["midfine"], Literal["coarse"]
]

# Excluding Kosovo which is missing in the Ember dataset and Albania which is missing
# in ENTSO-E data.
__aggregate_region_map: dict[AggregateRegion, set[Zone]] = {
    EU27: {
        AUSTRIA,
        BELGIUM,
        BULGARIA,
        CROATIA,
        CYPRUS,
        CZECHIA,
        DENMARK,
        ESTONIA,
        FINLAND,
        FRANCE,
        GERMANY,
        GREECE,
        HUNGARY,
        ITALY,
        IRELAND,
        LATVIA,
        LITHUANIA,
        LUXEMBOURG,
        MALTA,
        NETHERLANDS,
        POLAND,
        PORTUGAL,
        ROMANIA,
        SLOVAKIA,
        SLOVENIA,
        SPAIN,
        SWEDEN,
    },
    BALKANS: {
        BOSNIA_HERZEGOVINA,
        BULGARIA,
        CROATIA,
        GREECE,
        MONTENEGRO,
        NORTH_MACEDONIA,
        ROMANIA,
        SERBIA,
    },
    BALTICS: {ESTONIA, LATVIA, LITHUANIA},
    BELUX: {BELGIUM, LUXEMBOURG},
    BENELUX: {BELGIUM, NETHERLANDS, LUXEMBOURG},
    BRITISH_ISLES: {GREAT_BRITAIN, IRELAND},
    CENTRAL_BALKAN: {BOSNIA_HERZEGOVINA, MONTENEGRO, SERBIA},
    EAST_BALKAN: {BULGARIA, NORTH_MACEDONIA, GREECE},
    ESTONIA_LATVIA: {ESTONIA, LATVIA},
    FRANCE_SWITZERLAND: {FRANCE, SWITZERLAND},
    IBERIA: {SPAIN, PORTUGAL},
    NORDICS: {SWEDEN, FINLAND, NORWAY},
    SOUTH: {HUNGARY, SLOVENIA},
    SOUTH_CENTRAL_BALKAN: {MONTENEGRO, SERBIA, BOSNIA_HERZEGOVINA},
    WEST: {FRANCE, LUXEMBOURG, NETHERLANDS, BELGIUM, SWITZERLAND},
    WEST_BALKAN: {CROATIA, SLOVENIA},
}

ALL_COUNTRIES: set[Zone] = __aggregate_region_map[EU27] | {
    BOSNIA_HERZEGOVINA,
    GREAT_BRITAIN,
    MONTENEGRO,
    NORTH_MACEDONIA,
    NORWAY,
    SERBIA,
    SWITZERLAND,
}

REGION_AGGREGATION_LEVELS: dict[GridAggregationLevel, set[AggregateRegion]] = {
    # No aggregation: 32 nodes in total.
    "none": set(),
    # Fine aggregation: ~25 nodes.
    "fine": {BELUX, BRITISH_ISLES, CENTRAL_BALKAN, ESTONIA_LATVIA, IBERIA, WEST_BALKAN},
    # Midfine aggregation: 18 nodes.
    "midfine": {
        BALTICS,
        BENELUX,
        BRITISH_ISLES,
        EAST_BALKAN,
        FRANCE_SWITZERLAND,
        IBERIA,
        NORDICS,
        SOUTH_CENTRAL_BALKAN,
        WEST_BALKAN,
    },
    # Coarse aggregation: 14 nodes.
    "coarse": {BALKANS, BALTICS, BRITISH_ISLES, IBERIA, NORDICS, SOUTH, WEST},
}


def get_aggregated_countries(region: AggregateRegion) -> set[Zone]:
    if region not in __aggregate_region_map:
        raise Exception(f"Unknown aggregate region {region} used")
    return __aggregate_region_map[region]

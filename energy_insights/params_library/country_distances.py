"""
Provides constants for country distances in km (useful for pricing interconnectors).
"""

from typing import Optional

from ..region import *

# A very simple heuristics: required transmission distance between two countries is assumed 80% of
# the distance of the capitals.
_transmission_distance_ratio = 0.8

# Matrices of capital distances in km (overland and overseas).
# TODO: Store only half of the matrix (using lexicographic ordering of country codes, storing
# distances from lower-ranked to higher-ranked countries). Or perhaps just store the coordinates of
# capitals and calculate the great circle distance on the fly. That would make it easier to
# maintain, update and verify.
_OVERLAND: dict[Region, dict[Region, float]] = {
    FRANCE: {GERMANY: 878, SPAIN: 1056, ITALY: 1105, BELGIUM: 266,
             SWITZERLAND: 435, LUXEMBOURG: 288},
    GERMANY: {FRANCE: 878, BELGIUM: 656, NETHERLANDS: 576, AUSTRIA: 523, POLAND: 517, CZECHIA: 253,
              DENMARK: 358, SWITZERLAND: 753, LUXEMBOURG: 600},
    SPAIN: {FRANCE: 1056, PORTUGAL: 503},
    ITALY: {FRANCE: 1105, SWITZERLAND: 692, AUSTRIA: 762, SLOVENIA: 490},
    BELGIUM: {FRANCE: 266, GERMANY: 656, NETHERLANDS: 173, LUXEMBOURG: 185},
    LUXEMBOURG: {BELGIUM: 185, FRANCE: 288, GERMANY: 600},
    SWITZERLAND: {GERMANY: 753, FRANCE: 435, ITALY: 692, AUSTRIA: 680},
    NETHERLANDS: {BELGIUM: 173, GERMANY: 576},
    PORTUGAL: {SPAIN: 503},
    GREECE: {ALBANIA: 445, NORTH_MACEDONIA: 482, BULGARIA: 526, TURKEY: 561},
    AUSTRIA: {GERMANY: 523, SWITZERLAND: 680, ITALY: 762, SLOVENIA: 277, HUNGARY: 213,
              CZECHIA: 253, SLOVAKIA: 55},
    POLAND: {GERMANY: 517, CZECHIA: 516, SLOVAKIA: 534, UKRAINE: 688, LITHUANIA: 392},
    SWEDEN: {NORWAY: 417, FINLAND: 395},
    NORWAY: {SWEDEN: 417, FINLAND: 791},
    FINLAND: {SWEDEN: 395, NORWAY: 791},
    DENMARK: {GERMANY: 358},
    CZECHIA: {GERMANY: 253, SLOVAKIA: 292, POLAND: 516, AUSTRIA: 253},
    SLOVAKIA: {CZECHIA: 292, AUSTRIA: 55, HUNGARY: 161, POLAND: 534, UKRAINE: 1005},
    ESTONIA: {LATVIA: 282},
    LATVIA: {ESTONIA: 282, LITHUANIA: 260},
    LITHUANIA: {LATVIA: 260, POLAND: 392},
    SLOVENIA: {ITALY: 490, AUSTRIA: 277, HUNGARY: 383, CROATIA: 117},
    HUNGARY: {SLOVAKIA: 161, AUSTRIA: 213, SLOVENIA: 383, CROATIA: 300, SERBIA: 317, ROMANIA: 642,
              UKRAINE: 900},
    BULGARIA: {GREECE: 526, NORTH_MACEDONIA: 170, SERBIA: 331, ROMANIA: 297, TURKEY: 504},
    ROMANIA: {HUNGARY: 642, SERBIA: 450, BULGARIA: 297, UKRAINE: 745, MOLDOVA: 358},
    UKRAINE: {POLAND: 688, SLOVAKIA: 1005, HUNGARY: 900, ROMANIA: 745, MOLDOVA: 400},
    BOSNIA_HERZEGOVINA: {CROATIA: 290, SERBIA: 197, MONTENEGRO: 170},
    ALBANIA: {NORTH_MACEDONIA: 153, MONTENEGRO: 131, GREECE: 445, SERBIA: 389},
    CROATIA: {BOSNIA_HERZEGOVINA: 290, SERBIA: 368, MONTENEGRO: 459, SLOVENIA: 117, HUNGARY: 300},
    MONTENEGRO: {BOSNIA_HERZEGOVINA: 170, CROATIA: 459, SERBIA: 282, ALBANIA: 131},
    NORTH_MACEDONIA: {SERBIA: 322, BULGARIA: 170, ALBANIA: 153, GREECE: 482},
    SERBIA: {BOSNIA_HERZEGOVINA: 197, CROATIA: 368, MONTENEGRO: 282, NORTH_MACEDONIA: 322,
             HUNGARY: 317, ROMANIA: 450, BULGARIA: 331, ALBANIA: 389},
    TURKEY: {GREECE: 561, BULGARIA: 504},
    MOLDOVA: {UKRAINE: 400, ROMANIA: 358},
}

_OVERSEAS: dict[Region, dict[Region, float]] = {
    GREAT_BRITAIN: {FRANCE: 343, IRELAND: 464, GERMANY: 930, SPAIN: 1264, BELGIUM: 320,
                    NETHERLANDS: 357, SWEDEN: 1434, NORWAY: 1145, DENMARK: 962},
    IRELAND: {GREAT_BRITAIN: 464, FRANCE: 782},
    FRANCE: {GREAT_BRITAIN: 343, IRELAND: 782},
    GERMANY: {GREAT_BRITAIN: 930, SWEDEN: 808, NORWAY: 832},
    SPAIN: {GREAT_BRITAIN: 1264},
    BELGIUM: {GREAT_BRITAIN: 320},
    NETHERLANDS: {GREAT_BRITAIN: 357, NORWAY: 908, DENMARK: 620},
    POLAND: {SWEDEN: 806, FINLAND: 916, DENMARK: 670},
    SWEDEN: {DENMARK: 522, GERMANY: 808, POLAND: 806, ESTONIA: 381,
             LATVIA: 440, LITHUANIA: 676, GREAT_BRITAIN: 1434},
    NORWAY: {DENMARK: 483, NETHERLANDS: 908, GREAT_BRITAIN: 1145, GERMANY: 832},
    FINLAND: {ESTONIA: 80, POLAND: 916},
    DENMARK: {SWEDEN: 522, NORWAY: 483, GREAT_BRITAIN: 962, POLAND: 670, NETHERLANDS: 620},
    ESTONIA: {FINLAND: 80, SWEDEN: 381},
    LATVIA: {SWEDEN: 440},
    LITHUANIA: {SWEDEN: 676},
    GREECE: {CYPRUS: 915, ITALY: 1054},
    ITALY: {GREECE: 1054, MONTENEGRO: 563, MALTA: 692},
    MALTA: {ITALY: 692},
    MONTENEGRO: {ITALY: 563},
    TURKEY: {CYPRUS: 532},
    CYPRUS: {GREECE: 915, TURKEY: 532},
}


def _get_capital_distance(region_from: Region,
                          region_to: Region,
                          factor: float = 1) -> Optional[tuple[float, bool]]:
    """
    Returns a couple encoding the distance between the capitals of two specified regions or None if
    the distance is unknown (meaning the regions are not adjacent overland and not truly adjacent
    overseas).

    The first element of the tuple is the distance in km, the second element of the tuple is a bool
    whether the regions are adjacent overland.
    """
    if region_from in _OVERLAND and region_to in _OVERLAND[region_from]:
        assert _OVERLAND[region_from][region_to] == _OVERLAND[region_to][region_from], \
            f"the matrix of overland distances in not symmetric for {region_to} and {region_from}"
        return (_OVERLAND[region_from][region_to] * factor, True)
    if region_from in _OVERSEAS and region_to in _OVERSEAS[region_from]:
        assert _OVERSEAS[region_from][region_to] == _OVERSEAS[region_to][region_from], \
            f"the matrix of overseas distances in not symmetric for {region_to} and {region_from}"
        return (_OVERSEAS[region_from][region_to] * factor, False)
    return None


def get_transmission_distance_km(region_from: Region, region_to: Region) -> Optional[tuple[float, bool]]:
    """
    Returns a couple encoding the transmission distance between two specified regions or None if the
    distance is unknown (meaning the regions are not adjacent overland and not truly adjacent
    overseas).

    The first element of the tuple is the distance in km, the second element of the tuple is a bool
    whether the regions are adjacent overland.
    """
    return _get_capital_distance(region_from, region_to, factor=_transmission_distance_ratio)

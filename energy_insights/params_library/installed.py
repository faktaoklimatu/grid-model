"""
Provides installed capacities for selected resources in the grid. For each year, these are the installed capacities _at the end of the year_.
"""

from typing import Optional

import pandas as pd

from ..region import *
from ..sources.basic_source import BasicSourceType

__zero = {
    BasicSourceType.SOLAR: 0,
    BasicSourceType.OFFSHORE: 0,
    BasicSourceType.ONSHORE: 0,
    BasicSourceType.NUCLEAR: 0,
    BasicSourceType.HYDRO: 0,
}

__cz_2021 = {
    BasicSourceType.SOLAR: 2.066,
    BasicSourceType.OFFSHORE: 0,
    BasicSourceType.ONSHORE: 0.335,
    BasicSourceType.NUCLEAR: 4.047,
    BasicSourceType.HYDRO: 1.105,
}

__sk_2020 = {
    BasicSourceType.SOLAR: 0.53,
    BasicSourceType.OFFSHORE: 0,
    BasicSourceType.ONSHORE: 0,
    BasicSourceType.NUCLEAR: 2,
    BasicSourceType.HYDRO: 1.63,
}

__de_now = {BasicSourceType.HYDRO: 4.937}
__at_now = {BasicSourceType.OFFSHORE: 0, BasicSourceType.NUCLEAR: 0}
__pl_constants = {BasicSourceType.OFFSHORE: 0, BasicSourceType.NUCLEAR: 0}

_installed_gw = {
    CZECHIA: {
        2016: __cz_2021 | {BasicSourceType.ONSHORE: 0.28, BasicSourceType.SOLAR: 2.03},
        2017: __cz_2021 | {BasicSourceType.ONSHORE: 0.31},
        2018: __cz_2021 | {BasicSourceType.ONSHORE: 0.32},
        2019: __cz_2021,
        2020: __cz_2021,
        2021: __cz_2021,
        2022: __cz_2021,
    },
    GERMANY: {  # Based on energy-charts.info.
        2016: __de_now
        | {
            BasicSourceType.SOLAR: 40.679,
            BasicSourceType.OFFSHORE: 4.152,
            BasicSourceType.ONSHORE: 45.283,
            BasicSourceType.NUCLEAR: 10.8,
        },
        2017: __de_now
        | {
            BasicSourceType.SOLAR: 42.292,
            BasicSourceType.OFFSHORE: 6.396,
            BasicSourceType.ONSHORE: 52.447,
            BasicSourceType.NUCLEAR: 10.8,
        },
        2018: __de_now
        | {
            BasicSourceType.SOLAR: 45.313,
            BasicSourceType.OFFSHORE: 6.396,
            BasicSourceType.ONSHORE: 52.447,
            BasicSourceType.NUCLEAR: 9.516,
        },
        2019: __de_now
        | {
            BasicSourceType.SOLAR: 49.096,
            BasicSourceType.OFFSHORE: 7.528,
            BasicSourceType.ONSHORE: 53.193,
            BasicSourceType.NUCLEAR: 9.516,
        },
        2020: __de_now
        | {
            BasicSourceType.SOLAR: 54.066,
            BasicSourceType.OFFSHORE: 7.741,
            BasicSourceType.ONSHORE: 54.841,
            BasicSourceType.NUCLEAR: 8.114,
        },
        2021: __de_now
        | {
            BasicSourceType.SOLAR: 58.984,
            BasicSourceType.OFFSHORE: 7.774,
            BasicSourceType.ONSHORE: 56.271,
            BasicSourceType.NUCLEAR: 8.114,
        },
        2022: __de_now
        | {
            BasicSourceType.SOLAR: 65.517,
            BasicSourceType.OFFSHORE: 8.057,
            BasicSourceType.ONSHORE: 58.146,
            BasicSourceType.NUCLEAR: 4.056,
        },
    },
    GREAT_BRITAIN: {
        # Nuclear capacities from Ember:
        # https://ember-climate.org/data/data-tools/data-explorer/
        2018: {BasicSourceType.NUCLEAR: 9.26},
        2019: {BasicSourceType.NUCLEAR: 9.26},
        2020: {BasicSourceType.NUCLEAR: 9.26},
        2021: {BasicSourceType.NUCLEAR: 7.83},
        2022: {BasicSourceType.NUCLEAR: 7.83},
    },
    AUSTRIA: {  # Based on energy-charts.info.
        # TODO: Although real solar production in 2020 was around 2 TWh,
        # ENTSO-E data only show 0.8 TWh. Make sure to fix that so that production gets correctly
        # extrapolated.
        2019: __at_now
        | {
            BasicSourceType.SOLAR: 1.33,
            BasicSourceType.ONSHORE: 3.13,
            BasicSourceType.HYDRO: 5.72 + 2.44,
        },
        2020: __at_now
        | {
            BasicSourceType.SOLAR: 1.85,
            BasicSourceType.ONSHORE: 3.2,
            BasicSourceType.HYDRO: 5.94 + 2.43,
        },
        2021: __at_now
        | {
            BasicSourceType.SOLAR: 2.5,
            BasicSourceType.ONSHORE: 3.5,
            BasicSourceType.HYDRO: 5.84 + 2.47,
        },
        2022: __at_now
        | {
            BasicSourceType.SOLAR: 3.27,
            BasicSourceType.ONSHORE: 3.57,
            BasicSourceType.HYDRO: 5.90 + 2.77,
        },
    },
    BELGIUM: {
        # Nuclear capacities from Ember:
        # https://ember-climate.org/data/data-tools/data-explorer/
        2018: {BasicSourceType.NUCLEAR: 5.92},
        2019: {BasicSourceType.NUCLEAR: 5.93},
        2020: {BasicSourceType.NUCLEAR: 5.94},
        2021: {BasicSourceType.NUCLEAR: 5.85},
        2022: {BasicSourceType.NUCLEAR: 5.84},
    },
    BULGARIA: {
        # Nuclear capacities from Ember:
        # https://ember-climate.org/data/data-tools/data-explorer/
        2018: {BasicSourceType.NUCLEAR: 2.01},
        2019: {BasicSourceType.NUCLEAR: 2.01},
        2020: {BasicSourceType.NUCLEAR: 2.01},
        2021: {BasicSourceType.NUCLEAR: 2.01},
        2022: {BasicSourceType.NUCLEAR: 2.01},
    },
    # Based on energy-charts.info.
    DENMARK: {
        2020: __zero
        | {
            BasicSourceType.SOLAR: 1.3,
            BasicSourceType.OFFSHORE: 1.7,
            BasicSourceType.ONSHORE: 4.48,
        },
        2021: __zero
        | {
            BasicSourceType.SOLAR: 1.54,
            BasicSourceType.OFFSHORE: 2.31,
            BasicSourceType.ONSHORE: 4.64,
        },
    },
    POLAND: {  # Based on energy-charts.info.
        2019: __pl_constants
        | {
            BasicSourceType.SOLAR: 1.31,
            BasicSourceType.ONSHORE: 5.95,
            BasicSourceType.HYDRO: 0.61,
        },
        2020: __pl_constants
        | {
            BasicSourceType.SOLAR: 3.47,
            BasicSourceType.ONSHORE: 6.57,
            BasicSourceType.HYDRO: 0.61,
        },
        2021: __pl_constants
        | {
            BasicSourceType.SOLAR: 6.66,
            BasicSourceType.ONSHORE: 7.95,
            BasicSourceType.HYDRO: 0.78,
        },
        2022: __pl_constants
        | {
            BasicSourceType.SOLAR: 10.41,
            BasicSourceType.ONSHORE: 8.97,
            BasicSourceType.HYDRO: 0.78,
        },
    },
    ROMANIA: {
        # Ember gives 1.3 GW for nuclear in Romania, but production
        # in ENTSO-E goes up to 1.43, so we bump up the assumed
        # installed capacity by a small bit.
        2018: {BasicSourceType.NUCLEAR: 1.45},
        2019: {BasicSourceType.NUCLEAR: 1.45},
        2020: {BasicSourceType.NUCLEAR: 1.45},
        2021: {BasicSourceType.NUCLEAR: 1.45},
        2022: {BasicSourceType.NUCLEAR: 1.45},
    },
    SLOVAKIA: {  # Based on energy-charts.info.
        2018: __sk_2020,
        2019: __sk_2020,
        2020: __sk_2020,
        2021: __sk_2020,
        2022: __sk_2020,
    },
    SPAIN: {
        # Nuclear capacities from Ember:
        # https://ember-climate.org/data/data-tools/data-explorer/
        2018: {BasicSourceType.NUCLEAR: 7.12},
        2019: {BasicSourceType.NUCLEAR: 7.12},
        2020: {BasicSourceType.NUCLEAR: 7.12},
        2021: {BasicSourceType.NUCLEAR: 7.12},
        2022: {BasicSourceType.NUCLEAR: 7.12},
    },
    SWITZERLAND: {
        # Nuclear capacities from Ember:
        # https://ember-climate.org/data/data-tools/data-explorer/
        2018: {BasicSourceType.NUCLEAR: 3.33},
        2019: {BasicSourceType.NUCLEAR: 3.33},
        2020: {BasicSourceType.NUCLEAR: 3.33},
        2021: {BasicSourceType.NUCLEAR: 2.96},
        2022: {BasicSourceType.NUCLEAR: 2.96},
    },
    SWEDEN: {
        # Nuclear capacities from Ember:
        # https://ember-climate.org/data/data-tools/data-explorer/
        2018: {BasicSourceType.NUCLEAR: 8.66},
        2019: {BasicSourceType.NUCLEAR: 8.62},
        2020: __zero
        | {
            # Based on https://www.statista.com/statistics/1394486/solar-photovoltaic-capacity-in-sweden/.
            BasicSourceType.SOLAR: 1.107,
            # Based on https://en.wikipedia.org/wiki/List_of_offshore_wind_farms_in_Sweden.
            BasicSourceType.OFFSHORE: 0.19,
            BasicSourceType.ONSHORE: 10,
            BasicSourceType.HYDRO: 16.33,
            BasicSourceType.NUCLEAR: 7.78,
        },
        2021: {BasicSourceType.NUCLEAR: 6.9},
        2022: {BasicSourceType.NUCLEAR: 6.9},
    },
    FINLAND: {
        2020: __zero
        | {
            # Based on https://public.tableau.com/views/IRENARETimeSeries/Charts.
            BasicSourceType.SOLAR: 0.318,
            # Based on https://en.wikipedia.org/wiki/Wind_power_in_Finland#Offshore_wind.
            BasicSourceType.OFFSHORE: 0.044,
            # Based on https://public.tableau.com/views/IRENARETimeSeries/Charts.
            BasicSourceType.ONSHORE: 2.586,
            BasicSourceType.HYDRO: 3.15,
            BasicSourceType.NUCLEAR: 2.79,
        }
    },
    NORWAY: {
        2020: __zero
        | {
            # Based on https://public.tableau.com/views/IRENARETimeSeries/Charts.
            BasicSourceType.SOLAR: 0.160,
            # Based on https://public.tableau.com/views/IRENARETimeSeries/Charts.
            BasicSourceType.ONSHORE: 4.03,
            BasicSourceType.HYDRO: 6.68 + 26.68,
        }
    },
    ESTONIA: {
        2020: __zero
        | {  # Based on https://public.tableau.com/views/IRENARETimeSeries/Charts.
            BasicSourceType.SOLAR: 0.207,
            BasicSourceType.ONSHORE: 0.317,
            BasicSourceType.HYDRO: 0.08,
        }
    },
    LATVIA: {
        2020: __zero
        | {  # Based on https://public.tableau.com/views/IRENARETimeSeries/Charts.
            BasicSourceType.SOLAR: 0.005,
            BasicSourceType.ONSHORE: 0.078,
            BasicSourceType.HYDRO: 1.586,
        }
    },
    LITHUANIA: {
        2020: __zero
        | {  # Based on https://public.tableau.com/views/IRENARETimeSeries/Charts.
            BasicSourceType.SOLAR: 0.164,
            BasicSourceType.ONSHORE: 0.540,
            BasicSourceType.HYDRO: 0.170,
        }
    },
}


def get_installed_gw(
    country: Zone, year: int
) -> Optional[dict[BasicSourceType, float]]:
    result = _installed_gw.get(country, {}).get(year)
    # FIXME: Temporarily commented out. Find a better way to scale
    # ENTSO-E production down the road.
    # for source in BasicSourceType:
    #     if source != BasicSourceType.WIND:
    #         assert source in result, f"installed_gw must define {source} type"
    return result


# Mapping between the keys of the factors dictionary and the
# "Technology - Grouped" column from the Ember NG dataset.
__ember_ng_technologies_map: dict[BasicSourceType, str] = {
    BasicSourceType.SOLAR: "Solar",
    BasicSourceType.ONSHORE: "Onshore wind",
    BasicSourceType.OFFSHORE: "Offshore wind",
    BasicSourceType.NUCLEAR: "Nuclear",
    BasicSourceType.HYDRO: "Hydropower",
}


def load_installed_and_production_from_ember_ng(
    df: pd.DataFrame, scenario: str, year: int, country: Region
) -> dict[BasicSourceType, tuple[float, float]]:
    """
    Load installed capacities and annual production for basic
    sources from the Ember New Generation [1] raw data file.

    Arguments:
        df: Pandas data frame of the Ember New Generation dataset.
        scenario: Name of scenario to load.
        year: Target year for installed capacities and production.
            Available years range between 2020 and 2050 in 5-year
            increments.
        country: Code of country whose capacities and production
            should get loaded.

    Returns:
        Dictionary of pairs for each available source. The first
        element of the pair is installed capacity in GW, the second
        is annual production in TWh.

    [1]: https://ember-climate.org/insights/research/new-generation/
    """
    # Validate arguments.
    if country not in df["Country"].unique():
        raise ValueError(
            f"Country ‘{country}’ not available in Ember New Generation dataset"
        )
    if scenario not in df["Scenario"].unique():
        raise ValueError(f"Invalid Ember New Generation scenario ‘{scenario}’")
    if year not in df["Trajectory year"].unique():
        raise ValueError(f"Invalid Ember New Generation target year ‘{year}’")

    df = df[(df["Scenario"] == scenario) & (df["Country"] == country)]

    installed_gw_and_production_twh: dict[BasicSourceType, tuple[float, float]] = {}

    for key, technology in __ember_ng_technologies_map.items():
        # Computing factors from generation (and not installed capacities) is useful for wind where
        # utilization will grow compare to baseline values). For other sources, this should not
        # matter much.
        df_installed = df[
            (df["KPI"] == "Installed capacities - power generation")
            & (df["Technology - Grouped"] == technology)
        ]
        df_production = df[
            (df["KPI"] == "Power generation (by technology)")
            & (df["Technology - Grouped"] == technology)
        ]
        # Some sources are split among multiple rows. Therefore, sum
        # the numbers by the "Technology - Grouped" column.
        installed_gw_and_production_twh[key] = (
            df_installed[df_installed["Trajectory year"] == year]["Result"].sum(),
            df_production[df_production["Trajectory year"] == year]["Result"].sum()
            / 1e3,
        )

    return installed_gw_and_production_twh

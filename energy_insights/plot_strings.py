""" Shared code for names and titles of plots based on params. """

from itertools import islice

from .params_library.load_factors import LoadFactors
from .region import Region
from .sources.basic_source import BasicSourceType, Source

MAX_COUNTRIES: int = 6


def _get_shared_strings(params, countries):
    title = ""
    name = '-'.join(countries)

    if 'analysis_name' in params:
        title += params['analysis_name'] + " - "

    if 'name' in params:
        title += params['name']
        name += '-' + params['name']

    if params.get("optimize_capex", False):
        title += ' ▽'
        name += '-opt-capex'

    return title, name


def _get_capacities_factors(factors: LoadFactors, installed: dict[BasicSourceType, float]):
    def __cap(key: BasicSourceType) -> str:
        installed_gw = installed.get(key, 0) / 1000
        return f"{installed_gw:.1f}"

    factors_capacities_str = [
        f"S={__cap(BasicSourceType.SOLAR)} GW",
        f"W={__cap(BasicSourceType.ONSHORE)}/{__cap(BasicSourceType.OFFSHORE)} GW",
        f"N={__cap(BasicSourceType.NUCLEAR)} GW",
        f"H={__cap(BasicSourceType.HYDRO)} GW",
    ]

    if 'load' in factors:
        factors_capacities_str.append(f"L={factors['load']:.1f}×")
    else:
        factors_capacities_str.append(
            f"L={factors['load_base']:.1f}×"
        )

    return ", ".join(factors_capacities_str)


def _get_subtitle(factors_separate: dict[Region, LoadFactors],
                  installed_separate: dict[Region, dict],
                  include_values: bool):
    value_fmt = " = {:.1f} TWh" if include_values else ""

    generation_format = [
        "solar" + value_fmt,
        "wind" + value_fmt,
        "nuclear" + value_fmt,
        "hydro" + value_fmt,
    ]

    capacities_factors_str = "\n".join(
        country + ": " + _get_capacities_factors(factors, installed_separate[country])
        for country, factors in islice(factors_separate.items(), 0, MAX_COUNTRIES))

    return "demand" + value_fmt, ", ".join(generation_format), capacities_factors_str


def get_grid_strings(params, factors_separate: dict[Region, LoadFactors],
                     installed_separate: dict[Region, dict]):
    title, name = _get_shared_strings(params, factors_separate.keys())
    demand_format, subtitle_format, capacities_factors_str = _get_subtitle(
        factors_separate, installed_separate, include_values=True)

    return title + " with " + demand_format, subtitle_format, capacities_factors_str, name

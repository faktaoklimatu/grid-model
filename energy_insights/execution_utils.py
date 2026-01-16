"""Shared code for execution and notebooks."""

import os
from functools import cache
from pathlib import Path
from typing import Optional, Union

import matplotlib
import pandas as pd

from .country_grid import CountryGrid
from .country_grid_stats import CountryGridStats, StatOutput
from .grid_optimization import CountryProblem, GridOptimization, grids_from_problems
from .grid_plot_utils import Keys
from .heat_demand_estimator import HeatDemandEstimator
from .hourly_data_extrapolator import HourlyDataExtrapolator
from .loaders import EntsoeLoader, PecdLoader
from .logging import get_logger
from .params_library import basic_source, flexible_source, storage
from .params_library.installed import get_installed_gw
from .params_library.interconnectors import get_interconnectors
from .params_utils import (
    get_country_aggregate,
    get_country_or_aggregate,
    merge_config_into_scenario,
)
from .plot_strings import get_grid_strings
from .plot_utils import get_scenario_out_dir, get_analysis_out_dir
from .region import AggregateRegion, CZECHIA, Region, Zone
from .solver_util import Solver, get_solver_by_name
from .sources.basic_source import get_basic_sources
from .sources.flexible_source import get_flexible_sources
from .sources.reserves import ReservesRequirements
from .sources.storage import get_storage
from .temperatures_loader import TemperaturesLoader
from .yearly_filter import YearlyFilter
from .yearly_grid_plot import YearlyGridPlot

logger = get_logger(__name__)

# Use a non-interactive Matplotlib backend to prevent memory leaks
# when running from Jupyter notebook, see the documentation for details
# https://matplotlib.org/stable/users/faq.html#work-with-threads
# and https://matplotlib.org/stable/users/explain/figure/backends.html#selecting-a-backend
matplotlib.use("agg")


def append_stats_to_output(
    stats: list[StatOutput], name: str, out_dir: Path, update=False
) -> None:
    long_name = out_dir / f"{name}.csv"
    wide_name = out_dir / f"{name}-pivot.csv"

    df_long = pd.DataFrame(stats)

    # Append to the existing CSV if it's present.
    if long_name.is_file():
        df_long_existing = pd.read_csv(long_name, index_col=0)
        if update:
            incoming_scenarios = df_long["name"].unique().tolist()
            df_long_existing = df_long_existing[
                ~df_long_existing["name"].isin(incoming_scenarios)
            ]
        df_long = pd.concat([df_long_existing, df_long], ignore_index=True)

    df_long.to_csv(long_name)

    # Overwrite pivot table -- the data should be the same.
    df_wide = df_long.pivot(
        index=["name", "region", "season", "stat"], columns="source", values="val"
    )
    df_wide.to_csv(wide_name)


@cache
def get_entsoe_loader(data_path: Union[str, Path]) -> EntsoeLoader:
    return EntsoeLoader(data_path=data_path)


@cache
def get_extrapolator(
    entsoe_loader: EntsoeLoader, pecd_loader: PecdLoader
) -> HourlyDataExtrapolator:
    """Return one shared extrapolator (for loading the params as well
    as for building the model).
    """
    return HourlyDataExtrapolator(entsoe_loader=entsoe_loader, pecd_loader=pecd_loader)


@cache
def get_pecd_loader(data_path: Union[str, Path]) -> PecdLoader:
    return PecdLoader(data_path=data_path)


def optimize_runs(
    runs: list[dict],
    extrapolator: Optional[HourlyDataExtrapolator] = None,
    entsoe_loader: Optional[EntsoeLoader] = None,
    pecd_loader: Optional[PecdLoader] = None,
    root_dir="..",
) -> None:
    data_path = os.path.join(root_dir, "data")

    heat_estimator = HeatDemandEstimator(data_path=data_path)
    temperatures_loader = TemperaturesLoader(data_path=data_path)

    if not entsoe_loader:
        entsoe_loader = get_entsoe_loader(data_path)

    if not pecd_loader:
        pecd_loader = get_pecd_loader(data_path)

    if not extrapolator:
        extrapolator = get_extrapolator(entsoe_loader, pecd_loader)

    for run_number, run in enumerate(runs):
        config = run["config"]
        logger.info(f"Run number #{run_number}: {config['analysis_name']}")

        analysis_name = config.get("analysis_name")
        analysis_out_dir = get_analysis_out_dir(analysis_name, root_dir=root_dir)
        if analysis_name is None:
            analysis_name = "analysis"

        for scenario in run["scenarios"]:
            logger.info(f"Running scenario ‘{scenario['name']}’")

            params = merge_config_into_scenario(config, scenario)
            # Expand params from a library.
            if "year" in params:
                common_years = entsoe_years = [params["year"]]
                pecd_years: list[Optional[int]] = [None]
            else:
                common_years = params["common_years"]
                entsoe_years = params["entsoe_years"]
                assert len(common_years) == len(entsoe_years) and len(common_years) > 0
                pecd_years: list[Optional[int]] = params.get("pecd_years", [])
                assert len(pecd_years) == len(common_years)

            # Use PECD by default if pecd years are provided.
            pecd_target_year = params.get("pecd_target_year", 2025)

            if len(params["countries"]) > 1 and "interconnectors" not in params:
                logger.warning(f"Did you forget to specify interconnectors?")
            interconnectors = get_interconnectors(
                params.get("interconnectors", {}),
                {
                    get_country_or_aggregate(c, c_params)
                    for c, c_params in params["countries"].items()
                },
            )
            input_costs_global = params.get("input_costs", "current")
            name = "grid-optimization-{}".format(scenario["name"])
            optimize_capex = params.get("optimize_capex", False)
            optimize_ramp_up_costs = params.get("optimize_ramp_up_costs", False)
            optimize_heat = params.get("optimize_heat", False)
            preferred_solver: Optional[Solver] = get_solver_by_name(
                params.get("solver", "")
            )
            solver_timeout_minutes: Optional[int] = params.get(
                "solver_timeout_minutes", None
            )
            solver_shift_ipm_termination_by_orders: int = params.get(
                "solver_shift_ipm_termination_by_orders", 0
            )

            load_previous_solution = params.get("load_previous_solution", False)
            store_model = params.get("store_model", True)
            yearly_filter = YearlyFilter.build(params["filter"])

            problems: dict[Region, CountryProblem] = {}
            aggregates: dict[AggregateRegion, dict[Zone, CountryProblem]] = {}
            load_factors_separate: dict[Region, dict] = {}
            installed_separate: dict[Region, dict] = {}
            for country, country_params in params["countries"].items():
                logger.debug(f"Processing country {country}...")

                if (
                    load_previous_solution
                    and yearly_filter.regions
                    and country not in yearly_filter.regions
                ):
                    continue
                load_factors = country_params["load_factors"]
                load_factors_separate[country] = load_factors
                reserves: Optional[ReservesRequirements] = country_params.get(
                    "reserves"
                )
                load_pecd_segments_demand = country_params.get(
                    "load_pecd_segments_demand"
                )

                input_costs = country_params.get("input_costs", input_costs_global)

                # Types of sources.
                basic_sources = get_basic_sources(country_params["basic_sources"])
                flexible_sources = get_flexible_sources(
                    country_params["flexible_sources"], input_costs
                )
                storage = get_storage(country_params["storage"])
                pecd_normalization_factors = country_params.get(
                    "pecd_normalization_factors", {}
                )

                logger.debug(
                    "Capacities of basic sources: {}".format(
                        ", ".join(
                            f"{key} {source.capacity_mw:.0f}"
                            for key, source in basic_sources.items()
                        )
                    )
                )
                logger.debug(
                    "Capacities of flexible sources: {}".format(
                        ", ".join(
                            f"{key} {source.capacity_mw:.0f}"
                            for key, source in flexible_sources.items()
                        )
                    )
                )
                logger.debug(
                    "Capacities of storage units: {}".format(
                        ", ".join(
                            f"{key} {storage.capacity_mw:.0f}"
                            for key, storage in storage.items()
                        )
                    )
                )

                if "installed_gw" in country_params:
                    installed_map_gw = country_params["installed_gw"]
                else:
                    # TODO: Fix default installed params for multiple years.
                    installed_map_gw = get_installed_gw(country, common_years[0])

                installed_separate[country] = {
                    key: source.capacity_mw for key, source in basic_sources.items()
                }

                data = pd.DataFrame()
                for entsoe_year, pecd_year, common_year in zip(
                    entsoe_years, pecd_years, common_years
                ):
                    one_year_data = extrapolator.extrapolate_hourly_country_data(
                        country,
                        entsoe_year,
                        pecd_year,
                        common_year,
                        load_factors,
                        basic_sources,
                        installed_map_gw,
                        pecd_normalization_factors,
                        pecd_target_year,
                        load_nuclear_from_entsoe=True,
                        load_pecd_segments_demand=load_pecd_segments_demand,
                    )

                    # FIXME: This is ugly as hell. Temporary solution for
                    # the coal study 2025/26 re-run.
                    if country == CZECHIA and scenario["name"] == "2028-stress":
                        one_year_data[Keys.NUCLEAR] = (
                            one_year_data[Keys.NUCLEAR] - 510
                        ).clip(lower=0)

                    if data.empty:
                        data = one_year_data
                    else:
                        data = pd.concat([data, one_year_data])

                # TODO: Fix heat for multiple years.
                # TODO: Load temperature according to weather year rather than
                # the common year.
                heat_demand: bool = country_params.get("heat_demand", False)
                if heat_demand:
                    temperatures_profile = country_params["historic_temperatures"]
                    historic_hourly_temperatures = (
                        temperatures_loader.load_temperatures(
                            temperatures_profile, common_years[0]
                        )
                    )
                    current_hourly_temperatures = pecd_loader.load_temperatures(
                        country, pecd_years[0], common_years[0]
                    )
                    heat_demand_MW = heat_estimator.get_heat_demand_MW(
                        historic_hourly_temperatures,
                        current_hourly_temperatures,
                        country,
                        common_years[0],
                    )
                    data = data.join(heat_demand_MW.rename(Keys.HEAT_DEMAND))
                else:
                    data[Keys.HEAT_DEMAND] = 0

                # Make the sources more expensive according to normalization factors.
                for basic_type, factor in pecd_normalization_factors.items():
                    basic_sources[
                        basic_type
                    ].economics.overnight_costs_per_kw_eur *= factor
                    basic_sources[
                        basic_type
                    ].economics.fixed_o_m_costs_per_kw_eur *= factor

                grid = CountryGrid(
                    country,
                    data,
                    basic_sources,
                    flexible_sources,
                    storage,
                    len(common_years),
                    reserves,
                )
                problem = CountryProblem(
                    grid, optimize_capex, optimize_ramp_up_costs, optimize_heat
                )

                aggregate = get_country_aggregate(country_params)
                if aggregate is not None:
                    aggregates.setdefault(aggregate, {})
                    aggregates[aggregate][country] = problem
                else:
                    problems[country] = problem

            for aggregate_country, countries in aggregates.items():
                aggregate_problem = sum(countries.values())
                assert isinstance(
                    aggregate_problem, CountryProblem
                ), "there must be at least one country to aggregate"
                aggregate_problem.grid.country = aggregate_country
                problems[aggregate_country] = aggregate_problem

            title_format, subtitle_format, capacities_factors_str, name = (
                get_grid_strings(params, load_factors_separate, installed_separate)
            )
            out_dir = get_scenario_out_dir(
                params["name"], params.get("analysis_name", None), root_dir=root_dir
            )
            include_transmission_loss_in_price = params.get(
                "include_transmission_loss_in_price", False
            )

            optim = GridOptimization(
                problems=problems,
                interconnectors=interconnectors,
                out_dir=out_dir,
                include_transmission_loss_in_price=include_transmission_loss_in_price,
                load_previous_solution=load_previous_solution,
                store_model=store_model,
                preferred_solver=preferred_solver,
                solver_timeout_minutes=solver_timeout_minutes,
                solver_shift_ipm_termination_by_orders=solver_shift_ipm_termination_by_orders,
            )
            success = optim.optimize()

            if success:
                output = params["output"]
                compute_interconnector_capex = params.get(
                    "compute_interconnector_capex", False
                )

                complete_stats = []
                filtered_stats = []

                for country, problem in problems.items():
                    complete_stats += CountryGridStats(
                        country,
                        problem.grid,
                        interconnectors if compute_interconnector_capex else None,
                        params["name"],
                    ).get_stats_for_logging()

                only_aggregate: bool = output.get("regions", "aggregate") == "aggregate"
                grids_to_plot = CountryGrid.aggregate_grids(
                    CountryGrid.filter_grids(
                        grids_from_problems(problems), yearly_filter
                    ),
                    only_aggregate,
                )

                stats_to_plot: dict[Region, CountryGridStats] = {}
                for country, grid in grids_to_plot.items():
                    stat = CountryGridStats(
                        country,
                        grid,
                        interconnectors if compute_interconnector_capex else None,
                        params["name"],
                        import_ppa_price=params.get("import_ppa_price"),
                        group_colors=output.get("group_colors", False),
                    )
                    stats_to_plot[country] = stat
                    filtered_stats += stat.get_stats_for_logging()

                # Store the stats after each scenario so that no data
                # is lost if the kernel runs out of memory. Do not
                # regenerate and overwrite summaries if we're loading
                # from an existing solution.
                if not load_previous_solution:
                    append_stats_to_output(
                        complete_stats, f"{analysis_name}-complete", analysis_out_dir
                    )
                    append_stats_to_output(
                        filtered_stats, analysis_name, analysis_out_dir
                    )

                if output.get("format") is not None:
                    plot = YearlyGridPlot(
                        stats_to_plot,
                        common_years[0],
                        yearly_filter,
                        output,
                        title_format,
                        subtitle_format,
                        capacities_factors_str,
                        out_dir,
                        name,
                    )
                    plot.print_graph()

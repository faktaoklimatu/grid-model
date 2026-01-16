#!/usr/bin/env python
import argparse
import sys

from energy_insights.execution_utils import (
    get_entsoe_loader,
    get_pecd_loader,
    optimize_runs,
)
from energy_insights.loaders.pemmdb import Pemmdb2025Loader
from energy_insights.logging import get_logger, set_debug, setup_logging
from energy_insights.region import *
from energy_insights.scenarios.czech_coal import (
    cz_coal_scenarios,
    get_pemmdb_loader,
    make_scenario,
)

logger = get_logger()


def make_coal_run(
    args: argparse.Namespace, pemmdb_loader: Pemmdb2025Loader
) -> dict | None:
    pecd_year: str = args.pecd_year
    name = args.name
    aggregation_level = (
        None if args.aggregation_level == "none" else args.aggregation_level
    )

    scenarios = {
        name: spec for name, spec in cz_coal_scenarios.items() if name in args.SCENARIOS
    }

    if not scenarios:
        return

    format = None
    if args.plots:
        format = "svg" if args.final_plots else "png"
    if args.final_plots:
        plot_filter = {
            "countries": [CZECHIA],
            "days": [
                "2018-01-08",
                "2018-01-09",
                "2018-01-10",
                "2018-01-11",
                "2018-01-12",
                "2018-01-13",
                "2018-01-14",
                "2018-01-15",
                "2018-01-16",
                "2018-01-17",
                "2018-01-18",
                "2018-01-19",
                "2018-01-20",
                "2018-01-21",
            ],
        }
    else:
        plot_filter = {"week_sampling": 4, "countries": [CZECHIA]}

    return {
        "config": {
            "analysis_name": name,
            "common_years": [args.common_year],
            "entsoe_years": [args.entsoe_year],
            "pecd_years": [pecd_year],
            "filter": plot_filter,
            "output": {
                "format": format,
                "dpi": 150,
                "heat": args.optimize_heat and not args.final_plots,
                "size_y_week": 0.7,
                "parts": (
                    ["weeks"]
                    if args.final_plots
                    else ["titles", "weeks", "week_summary", "year_stats"]
                ),
                "regions": "separate",
                "group_colors": args.group_colors,
            },
            "optimize_capex": False,
            "optimize_heat": args.optimize_heat,
            "optimize_ramp_up_costs": True,
            "load_previous_solution": args.load_solution,
            "store_model": args.store_model,
        },
        "scenarios": [
            make_scenario(
                name,
                scenario_spec,
                pemmdb_loader=pemmdb_loader,
                entsoe_year=args.entsoe_year,
                aggregation_level=aggregation_level,
                optimize_heat=args.optimize_heat,
                include_reserves=args.with_reserves,
                lignite_price_groups=args.lignite_price_groups,
            )
            for name, scenario_spec in scenarios.items()
        ],
    }


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser()

    # Data parameters.
    parser.add_argument("--common-year", type=int, default=2018)
    # ENTSO-E has only data back to 2010, we need a fallback year for the load.
    # TODO: Try ENTSO-E 2020 & PECD 2009 -- leapness mismatch.
    # NOTE: ENTSO-E is now used for nuclear production only.
    parser.add_argument("--entsoe-year", type=int, default=2018)
    # NOTE: There's a mismatch between the weather years (common_year and
    # entsoe_year) and PECD year because we only have weather starting 2019,
    # but the PECD dataset ends in 2016.
    parser.add_argument("--pecd-year", default="WS1")
    parser.add_argument("--aggregation-level", default="coarse")

    # Optimization parameters.
    parser.add_argument(
        "--optimize-coal", choices=["all", "cz", "none"], default="none"
    )
    parser.add_argument(
        "--optimize-heat", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--with-reserves", action="store_true")
    parser.add_argument("--lignite-price-groups", action="store_true")

    # Output parameters.
    parser.add_argument("--load-solution", action="store_true")
    parser.add_argument("--store-model", action="store_true")
    # Run name.
    parser.add_argument("--name", default="coaldown-core")
    # Scenario identifier override.
    parser.add_argument("--scenario-override", default=None)
    parser.add_argument("--plots", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--final-plots", action="store_true")
    parser.add_argument("--group-colors", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")

    # Scenarios specification.
    parser.add_argument("SCENARIOS", nargs="*")

    args = parser.parse_args()

    set_debug(args.verbose)

    entsoe_loader = get_entsoe_loader("data")
    pecd_loader = get_pecd_loader("data")
    pemmdb_loader = get_pemmdb_loader(root_dir=".")

    coal_run = make_coal_run(args, pemmdb_loader)

    if not coal_run:
        logger.error("No scenarios match specified filter, quitting")
        sys.exit(1)

    if args.scenario_override:
        if len(coal_run["scenarios"]) > 1:
            logger.error(
                "Cannot specify scenario name override for more than one scenario"
            )
            sys.exit(1)
        coal_run["scenarios"][0]["name"] = args.scenario_override

    optimize_runs(
        [coal_run], entsoe_loader=entsoe_loader, pecd_loader=pecd_loader, root_dir="."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted by user")
        sys.exit(130)

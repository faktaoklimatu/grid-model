"""
Plots yearly stats of grid production into one combined figure.
"""

from enum import Enum
from typing import Iterable, Optional
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib
import numpy as np
import pandas as pd

from .grid_capex_utils import *
from .grid_plot_utils import *
from .color_map import ColorMap
from .country_grid import CountryGrid
from .country_grid_stats import CountryGridStats, Season, StatType, StatPlotElement
from .region import AggregateRegion, Region
from .sources.basic_source import BasicSourceType, Source
from .sources.flexible_source import FlexibleSource, FlexibleSourceType
from .sources.storage import Storage, StorageUse
from .yearly_filter import YearlyFilter
from .yearly_plot import YearlyPlot

GENERATION_DISPLAY_THRESHOLD_MWH = 1e-3  # = 1 kWh
GENERATION_DISPLAY_THRESHOLD_TWH = GENERATION_DISPLAY_THRESHOLD_MWH / 1e6
"""Sources with annual generation below this threshold will be hidden
in summary plots. This is to account for limited optimization
accuracy."""

MAX_PRICE_TO_DISPLAY = 200
"""For legibility, limit the graph even if there is (expensive) energy not served"""


class YearlyGridPlot(YearlyPlot):

    class WeekPart(Enum):
        BASIC = 1
        FLEXIBLE = 2
        STORAGE = 3
        IMPORT = 4

    class PriceGraphData:
        def __init__(self, average_per_mwh=False) -> None:
            self._average_per_mwh = average_per_mwh
            self._capexes: list[float] = []
            self._opexes: list[float] = []
            self._colors: list[str] = []
            self._labels: list[str] = []
            self._weights: list[float] = []

        def add(self, capex: float, opex: float, color: str, type: str,
                weight: Optional[float] = None) -> None:
            self._capexes.append(capex)
            self._opexes.append(opex)
            self._colors.append(color)
            self._labels.append(type)
            if weight is not None:
                self._weights.append(weight)

        def print_graph(self,
                        plot: "YearlyGridPlot",
                        row: int,
                        column: int,
                        fmt: str,
                        ylim: Union[float, None],
                        title: str,
                        colspan=4,
                        print_label=True) -> None:
            indices = np.arange(len(self._capexes))
            rows_stats = plot._get_plot_params()['rows_stats']
            ax = plt.subplot2grid((rows_stats, YearlyPlot.columns_stats),
                                  (row, column + 1), colspan=colspan)
            # Add a fake set of empty bars to allow printing labels on the lower edge.
            p = ax.bar(indices, [0 for _ in self._capexes])

            # Print capex only of both capex and opex are non-zero.
            capexes_filtered = [cap if cap > 0 and op > 0 else 0
                                for op, cap in zip(self._opexes, self._capexes)]
            capex_labels = [fmt % capex if capex > 0 else "" for capex in capexes_filtered]
            ax.bar_label(p, labels=capex_labels, padding=0, fontsize=8)
            p = ax.bar(indices, self._capexes, color=self._colors)

            # Print opex only if non-zero.
            opex_labels = [fmt % opex if opex > 0 else "" for opex in self._opexes]
            ax.bar_label(p, labels=opex_labels, padding=4, fontsize=8)
            p = ax.bar(indices, self._opexes, color=self._colors,
                       bottom=self._capexes, alpha=0.6)

            total_price_labels = [fmt % (op + cap)
                                  for op, cap in zip(self._opexes, self._capexes)]
            ax.bar_label(p, labels=total_price_labels, padding=12, fontsize=10)

            plt.xticks(indices, self._labels, rotation=30)
            ax.margins(y=0.25)  # Make space for the ticks and labels
            # Allow for negative costs in case of net exporters.
            y_min = min(0, np.min(self._opexes))
            ax.set_ylim(y_min, ylim)
            # Draw horizontal axis line to anchor the zero point
            # in case of negative costs.
            if y_min < 0:
                ax.axhline(color="black", lw=0.5)

            if self._average_per_mwh:
                agg_capex = np.average(self._capexes, weights=self._weights)
                agg_opex = np.average(self._opexes, weights=self._weights)
                agg_title = f"Ø {title} per MWh"
                title = f"average {title} [EUR / MWh]"
                unit = "€"
                format = "{:.0f}"
            else:
                agg_capex = sum(self._capexes)
                agg_opex = sum(self._opexes)
                agg_title = f"Σ {title}"
                title = f"{title} [bil. EUR]"
                unit = "bil. €"
                format = "{:.2f}"
            agg_total = agg_capex + agg_opex

            plt.title(title, fontsize=14)
            plt.box(False)

            if print_label:
                label_format = format + " {}"
                subtitle = ""
                if agg_capex > 0 and agg_opex > 0:
                    subtitle_format = format + " capex + " + format + " opex"
                    subtitle = subtitle_format.format(agg_capex, agg_opex)
                plot._print_label(row, column, agg_title, label_format.format(agg_total, unit),
                                  "black", subtitle=subtitle)

    def __init__(
        self,
        stats: dict[Region, CountryGridStats],
        year: int,
        filter: YearlyFilter,
        output: dict,
        title_format: str,
        subtitle_format: str,
        capacities_str: str,
        out_dir: Path,
        name: str,
    ) -> None:
        # plot_heat is needed before calling super as _get_plot_params() is called from super init.
        self.plot_heat = output.get('heat', False)
        data_map = {country: stats.grid.data for country, stats in stats.items()}
        # plot_price is needed before calling super as _get_plot_params() is called from super init.
        self.plot_price = output.get('price', False)
        super().__init__(data_map, year, filter, output, out_dir, name)
        self.stats = stats
        self.title_format = title_format
        self.subtitle_format = subtitle_format
        self.capacities_str = capacities_str
        self.separate_excess = self.output.get('separate_excess', True)
        self.print_load_before_flexibility = self.output.get('load_before_flexibility', True)
        self.print_load_base = self.output.get('load_base', False)
        self.svg_output = self.output.get('format', "png") == "svg"

    def _get_plot_params(self) -> dict:
        week_graphs: dict[str, int] = {'electricity': 4}
        summary_spacer: int = 1
        if self.plot_price:
            week_graphs['price'] = 2
        if self.plot_heat:
            week_graphs['heat'] = 2
            summary_spacer += 2
        week_graphs['spacer'] = 1

        return {'size_x_week': self.output.get('size_x_week', 0.6),
                'size_y_week': self.output.get('size_y_week', 0.4),
                'colspan_week_summary': 1,
                'size_x_stats': 2.5,
                'size_y_stats': 2,
                'rows_stats': 8,
                'ylim_factor': 1.2,
                'week_graphs': week_graphs,
                'week_summary_graphs': {'electricity': 4, 'spacer': summary_spacer}}

    def _get_alpha_flexible(self) -> float:
        return self.output.get('alpha_flexible', 1.0)

    def _get_alpha_storage(self) -> float:
        return self.output.get('alpha_storage', 1.0)

    def _get_alpha_negative(self) -> float:
        return self.output.get('alpha_negative', 0.75)

    def _get_alpha_excess(self) -> float:
        return self.output.get('alpha_excess', 0.8)

    def _get_alpha_border(self) -> float:
        return self.output.get('alpha_border', 0.4)

    def _get_titles(self, region: Region, data: pd.DataFrame) -> tuple[str, str]:
        sums_twh = data.sum() / 1000000
        title = region + ": "
        if len(title) > 30:
            title += "\n"
        title += self.title_format.format(sums_twh[Keys.LOAD])
        subtitle = self.subtitle_format.format(
            sums_twh['Solar'], sums_twh['Wind'], sums_twh['Nuclear'], sums_twh['Hydro'])

        if not isinstance(region, AggregateRegion):
            grid = self.stats[region].grid

            if grid.flexible_sources:
                flexible_parts = []
                counter = 0
                for flexible_source in grid.flexible_sources.values():
                    sum_flexible = sums_twh[get_flexible_key(flexible_source)]
                    flexible_part = "{:s} = {:.2f} TWh".format(
                        flexible_source.type.value, sum_flexible)
                    if counter % 6 == 0:
                        flexible_part = "\n" + flexible_part
                    flexible_parts.append(flexible_part)
                    counter += 1
                subtitle += ", ".join(flexible_parts)

            total_net_import_twh = sums_twh['Net_Import']
            subtitle += f", import = {total_net_import_twh:.2f}"

        subtitle += "\n" + self.capacities_str

        return title, subtitle

    def _get_min_max(self, type: str, data: pd.DataFrame) -> tuple[float, float]:
        if type == 'heat':
            max_heat_demand_gw = data[Keys.HEAT_DEMAND].max() / 1000
            return 0, max_heat_demand_gw

        max_value = 0
        if 'max_gw' in self.output:
            max_value = self.output['max_gw']
        else:
            # A heuristic to show load large enough but also to account for excess total production.
            max_production_gw = data["Total"].max() / 1000
            max_load_gw = data[Keys.LOAD].max() / 1000
            if max_production_gw > 2 * max_load_gw:
                # Special case if production is far higher than load.
                max_value = (max_production_gw * 4) / 5
            elif max_production_gw > max_load_gw:
                max_value = (max_production_gw + max_load_gw * 2) / 3
            else:
                max_value = max_load_gw

        # Make sure the 0 line gets plotted.
        if 'min_gw' in self.output:
            min_value = self.output['min_gw']
        else:
            min_value = -0.1
            min_col = pd.Series(data=([0] * data.index.size), index=data.index)
            if 'Charging' in data.columns:
                min_col -= data["Charging"] / 1000
            if 'Export' in data.columns:
                min_col -= data["Export"] / 1000
            # Make sure the whole neg part is visible to make reading of curtailment possible.
            min_value = min(min_value, min_col.min())
        return min_value, max_value

    def _compute_week_ylim(self, type: str, data: pd.DataFrame) -> tuple[float, float]:
        if type == 'price':
            max_electricity_price = data[Keys.PRICE].max()
            return (0, min(max_electricity_price, MAX_PRICE_TO_DISPLAY))

        min_value, max_value = self._get_min_max(type, data)
        return (min_value, max_value)

    def _compute_summary_ylim(self, type: str, data: pd.DataFrame) -> tuple[float, float]:
        min_value, max_value = self._get_min_max(type, data)
        return (min_value / 1000, max_value / 1000)

    def _print_weekly_graph(self,
                            ax: plt.Axes,
                            region: Region,
                            weekly_index: list[float],
                            weekly_data: pd.DataFrame,
                            type: str) -> None:
        grid = self.stats[region].grid
        # This width is better for png output. For print, 0.95 might be better.
        bar_width = 0.9

        def _print_src(source: Source,
                       production_MW: pd.Series,
                       bottom_GW: pd.Series,
                       alpha: float):
            production_GW = production_MW / 1000
            ax.bar(weekly_index, production_GW, color=source.color,
                   alpha=alpha, bottom=bottom_GW, width=bar_width)
            bottom_GW += production_GW

        def _print_storage(storage_type: Storage,
                           discharging_MW: pd.Series,
                           charging_MW: pd.Series,
                           bottom_GW: pd.Series,
                           bottom_neg_GW: pd.Series):
            discharging_GW = discharging_MW / 1000
            ax.bar(weekly_index, discharging_GW, color=storage_type.color,
                   alpha=self._get_alpha_storage(), bottom=bottom_GW, width=bar_width)
            bottom_GW += discharging_GW

            charging_GW = charging_MW / 1000
            ax.bar(weekly_index, -charging_GW, color=storage_type.color,
                   alpha=self._get_alpha_storage() * self._get_alpha_negative(),
                   bottom=bottom_neg_GW, width=bar_width)
            bottom_neg_GW -= charging_GW

        def _print_storages(storage_list: Iterable[Storage], bottom, bottom_neg, plot_type: str):
            for storage in storage_list:
                discharging_MW = weekly_data[get_discharging_key(storage)]
                charging_MW = weekly_data[get_charging_key(storage)]

                if storage.use == StorageUse.POWER_TO_HEAT and plot_type == "heat":
                    # Show P2H as discharging (to heat) in heat plots and
                    # as charging (from electricity) otherwise.
                    # FIXME: Assuming power → heat only. Do we want to support
                    # heat → power as well?
                    discharging_MW = charging_MW * storage.charging_efficiency
                    charging_MW = pd.Series(0, index=charging_MW.index)

                _print_storage(storage, discharging_MW, charging_MW, bottom, bottom_neg)

        if type == "heat":
            bottom_heat = pd.Series(data=0, index=weekly_data.index)
            bottom_heat_neg = pd.Series(data=0, index=weekly_data.index)
            for flexible_source in grid.flexible_sources.values():
                if flexible_source.heat is not None:
                    _print_src(flexible_source,
                               weekly_data[get_flexible_heat_key(flexible_source)],
                               bottom_heat, self._get_alpha_flexible())

            heat_storages = (
                storage for storage in grid.storage.values()
                if storage.use in (StorageUse.HEAT, StorageUse.POWER_TO_HEAT)
            )
            _print_storages(heat_storages, bottom_heat, bottom_heat_neg, plot_type=type)

            ax.plot(weekly_index, weekly_data[Keys.HEAT_DEMAND] / 1000,
                    color=ColorMap.LOAD, lw=1, drawstyle="steps-mid")
            ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%d GWt"))
            ax.tick_params(axis="both", colors=ColorMap.LABELS)
            return

        if type == "price":
            # Plot import/export prices only if there's transmission
            # to speak of.
            if (weekly_data[Keys.NET_IMPORT].abs() > 1e-3).any():
                ax.plot(weekly_index, weekly_data[Keys.PRICE_EXPORT],
                        color=ColorMap.EXPORT_PRICE, linewidth=1, linestyle="--",
                        drawstyle="steps-mid")
                ax.plot(weekly_index, weekly_data[Keys.PRICE_IMPORT],
                        color=ColorMap.IMPORT_PRICE, linewidth=1, linestyle="--",
                        drawstyle="steps-mid")
            # Plot the stop price on top to make it better readable.
            ax.plot(weekly_index, weekly_data[Keys.PRICE],
                    color=ColorMap.LOAD, linewidth=1, drawstyle="steps-mid")
            ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%d EUR"))
            ax.axhline(color=ColorMap.GRAY, linewidth=1, linestyle=":")
            return

        week_parts = self.output.get("week_parts", {
            YearlyGridPlot.WeekPart.BASIC,
            YearlyGridPlot.WeekPart.FLEXIBLE,
            YearlyGridPlot.WeekPart.STORAGE,
            YearlyGridPlot.WeekPart.IMPORT,
        })

        nuclear = weekly_data["Nuclear"] / 1000
        hydro = weekly_data["Hydro"] / 1000
        wind_used = weekly_data[get_basic_used_key(BasicSourceType.WIND)] / 1000
        solar_used = weekly_data[get_basic_used_key(BasicSourceType.SOLAR)] / 1000
        wind_excess = weekly_data[get_basic_excess_key(BasicSourceType.WIND)] / 1000
        solar_excess = weekly_data[get_basic_excess_key(BasicSourceType.SOLAR)] / 1000

        bottom = np.zeros(len(weekly_data))
        bottom_neg = np.zeros(len(weekly_data))

        if YearlyGridPlot.WeekPart.BASIC in week_parts:
            ax.bar(weekly_index, nuclear, color=ColorMap.NUCLEAR, width=bar_width)
            bottom += nuclear
            ax.bar(weekly_index, hydro, color=ColorMap.HYDRO, bottom=bottom, width=bar_width)
            bottom += hydro

            # Print right after / instead of HYDRO.
            # FIXME: If more types become ELECTRICITY_AS_BASIC, figure out better sorting.
            _print_storages([storage for storage in grid.storage.values()
                            if storage.use == StorageUse.ELECTRICITY_AS_BASIC],
                            bottom, bottom_neg, plot_type=type)

            ax.bar(weekly_index, wind_used, color=ColorMap.WIND, bottom=bottom, width=bar_width)
            bottom += wind_used
            if not self.separate_excess:
                ax.bar(weekly_index, wind_excess, color=ColorMap.WIND,
                       bottom=bottom, width=bar_width)
                bottom += wind_excess

            ax.bar(weekly_index, solar_used, color=ColorMap.SOLAR, bottom=bottom, width=bar_width)
            bottom += solar_used
            if not self.separate_excess:
                ax.bar(weekly_index, solar_excess, color=ColorMap.SOLAR,
                       bottom=bottom, width=bar_width)
                bottom += solar_excess

        if YearlyGridPlot.WeekPart.STORAGE in week_parts:
            _print_storages(
                [
                    storage for storage in grid.storage.values()
                    if storage.use in (StorageUse.ELECTRICITY, StorageUse.POWER_TO_HEAT)
                ],
                bottom,
                bottom_neg,
                plot_type=type
            )

        if YearlyGridPlot.WeekPart.FLEXIBLE in week_parts:
            for flexible_source in grid.flexible_sources.values():
                _print_src(flexible_source,
                           weekly_data[get_flexible_key(flexible_source)],
                           bottom, self._get_alpha_flexible())

        # This results in plotting _net_ import / export for each hour, consistently with summary
        # plots. This is needed for aggregate plots but can be somewhat misleading in separate plots
        # with transit countries.
        # TODO: Allow to configure whether we show the whole balance or just net import / export.
        if YearlyGridPlot.WeekPart.IMPORT in week_parts:
            net_import = weekly_data[Keys.NET_IMPORT] / 1000
            export_data = net_import.clip(upper=0)
            ax.bar(weekly_index, export_data, color=ColorMap.INTERCONNECTORS,
                   alpha=self._get_alpha_negative(), bottom=bottom_neg, width=bar_width)
            bottom_neg += export_data
            ax.plot(weekly_index, bottom_neg, color=ColorMap.INTERCONNECTORS_BORDER,
                    lw=0.5, drawstyle='steps-mid')

            import_data = net_import.clip(lower=0)
            ax.bar(weekly_index, import_data, color=ColorMap.INTERCONNECTORS,
                   bottom=bottom, width=bar_width)
            bottom += import_data
            ax.plot(weekly_index, bottom, color=ColorMap.INTERCONNECTORS_BORDER,
                    lw=0.5, alpha=self._get_alpha_border(), drawstyle='steps-mid')

        if YearlyGridPlot.WeekPart.BASIC in week_parts and self.separate_excess:
            # Draw a line that separates usable and excess sources.
            ax.plot(weekly_index, bottom, color=ColorMap.LOAD_WITH_ACCUMULATION_BACKGROUND,
                    lw=1, drawstyle='steps-mid')
            ax.plot(weekly_index, bottom, color=ColorMap.LOAD_WITH_ACCUMULATION,
                    lw=0.5, drawstyle='steps-mid')

            # Make sure excess production is always above load.
            tmp = pd.DataFrame(
                data={Keys.LOAD: weekly_data[Keys.LOAD] / 1000, "Bottom": bottom}, index=weekly_data.index)
            bottom = tmp[[Keys.LOAD, "Bottom"]].max(axis=1)
            if self.svg_output:
                ax.bar(weekly_index, wind_excess, color=ColorMap.WIND,
                       alpha=self._get_alpha_excess(), bottom=bottom, width=bar_width)
                bottom += wind_excess
                ax.bar(weekly_index, solar_excess, color=ColorMap.SOLAR,
                       alpha=self._get_alpha_excess(), bottom=bottom, width=bar_width)
                bottom += solar_excess
            else:
                ax.bar(weekly_index, wind_excess, edgecolor=ColorMap.WIND, color="white", linewidth=0,
                       alpha=self._get_alpha_excess(), hatch="//////////", bottom=bottom, width=bar_width)
                bottom += wind_excess
                ax.bar(weekly_index, solar_excess, edgecolor=ColorMap.SOLAR, color="white", linewidth=0,
                       alpha=self._get_alpha_excess(), hatch="//////////", bottom=bottom, width=bar_width)
                bottom += solar_excess

        if self.print_load_before_flexibility and Keys.LOAD_BEFORE_FLEXIBILITY in weekly_data:
            # Alternating dots of two contrasting colors (to work well on light as well as on dark background).
            ax.plot(weekly_index, weekly_data[Keys.LOAD_BEFORE_FLEXIBILITY] / 1000,
                    color=ColorMap.LOAD_BEFORE_FLEXIBILITY_BACKGROUND, lw=1, drawstyle='steps-mid')
            ax.plot(weekly_index, weekly_data[Keys.LOAD_BEFORE_FLEXIBILITY] / 1000,
                    color=ColorMap.LOAD_BEFORE_FLEXIBILITY, lw=1, ls=(0, (1, 1.5)),
                    drawstyle='steps-mid')

        if Keys.LOAD_BASE in weekly_data and self.print_load_base:
            # Load is split into heat pump demand and other load ("base" load).
            ax.plot(weekly_index, weekly_data[Keys.LOAD_BASE] / 1000,
                    color=ColorMap.HEAT_PUMPS, lw=1, drawstyle="steps-mid")

        ax.plot(weekly_index, (weekly_data[Keys.LOAD]) / 1000,
                color=ColorMap.LOAD, lw=1, drawstyle="steps-mid")

        ax.yaxis.set_major_formatter(mtick.FormatStrFormatter("%d GW"))
        ax.axhline(color="white", lw=1.5)
        ax.tick_params(axis="both", colors=ColorMap.LABELS)

    def _print_summary(self,
                       ax: plt.Axes,
                       region: Region,
                       data: pd.DataFrame,
                       ylim_min: float,
                       ylim_max: float,
                       type: str,
                       label: str,
                       weekly: bool) -> None:
        grid = self.stats[region].grid

        (
            load,
            nuclear,
            hydro,
            wind,
            solar,
            inflow,
            flexible,
            discharging,
            charging,
            outflow,
            excess_solar,
            excess_wind,
        ) = get_grid_balance(data, grid.flexible_sources)

        generation = nuclear + hydro + wind + solar

        self.label_even = False

        bottom_neg = 0
        self._with_label(-outflow, load, weekly, ax,
                         ax.bar(0, -outflow, label="Export", color=ColorMap.INTERCONNECTORS,
                                alpha=self._get_alpha_negative(), bottom=bottom_neg))
        bottom_neg -= outflow
        self._with_label(-charging, load, weekly, ax,
                         ax.bar(0, -charging, label="Charging", color=ColorMap.STORAGE,
                                alpha=self._get_alpha_storage() * self._get_alpha_negative(),
                                bottom=bottom_neg))
        bottom_neg -= charging

        bottom = 0
        self._with_label(nuclear, load, weekly, ax, ax.bar(0, nuclear, color=ColorMap.NUCLEAR))
        bottom += nuclear
        self._with_label(hydro, load, weekly, ax, ax.bar(
            0, hydro, color=ColorMap.HYDRO, bottom=bottom))
        bottom += hydro
        self._with_label(wind, load, weekly, ax, ax.bar(
            0, wind, label="Wind", color=ColorMap.WIND, bottom=bottom))
        bottom += wind
        self._with_label(solar, load, weekly, ax, ax.bar(
            0, solar, label="Solar", color=ColorMap.SOLAR, bottom=bottom))
        bottom += solar

        self._with_label(inflow, load, weekly, ax, ax.bar(
            0, inflow, label="Import", color=ColorMap.INTERCONNECTORS, bottom=bottom))
        bottom += inflow

        self._with_label(discharging, load, weekly, ax, ax.bar(
            0, discharging, label="Discharging", color=ColorMap.STORAGE,
            alpha=self._get_alpha_storage(), bottom=bottom))
        bottom += discharging

        for key, flexible_source in grid.flexible_sources.items():
            production = flexible[key]
            bar = ax.bar(
                0, production, label=flexible_source.type.value, color=flexible_source.color,
                alpha=self._get_alpha_flexible(), bottom=bottom
            )
            self._with_label(production, load, weekly, ax, bar)
            bottom += production

        if load > bottom:
            bottom = load
        self._with_label(excess_wind, load, weekly, ax, ax.bar(
            0, excess_wind, color=ColorMap.WIND,
            alpha=self._get_alpha_excess(), bottom=bottom))
        bottom += excess_wind
        self._with_label(excess_solar, load, weekly, ax, ax.bar(
            0, excess_solar, color=ColorMap.SOLAR,
            alpha=self._get_alpha_excess(), bottom=bottom))
        bottom += excess_solar

        ax.set_ylim(ylim_min, ylim_max)

        ax.yaxis.tick_right()
        bar_width = 0.4
        margin = 0.8
        xlim = bar_width + margin
        ax.set_xlim(-xlim, xlim)

        ax.set_xticks([])
        plt.box(False)

        yticks = [0, generation, load]
        plt.yticks(fontsize=8)
        ax.set_yticks(yticks)
        for tick in yticks:
            ax.plot([-bar_width, xlim], [tick, tick], lw=0.75, color="Black")

        if weekly and load == 0:
            ax.yaxis.set_major_formatter(mtick.FuncFormatter(
                lambda x, pos: "{:.0f} GWh".format(x*1000)))
        elif weekly:
            ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=load))
        else:
            ax.yaxis.set_major_formatter(mtick.FormatStrFormatter('%d TWh'))
        if label:
            plt.title(label, fontsize=14)

    def _print_residual_load(self,
                             data: pd.DataFrame,
                             label: str,
                             row: int,
                             column: int,
                             size: int = 2) -> None:
        series_MW = get_residual_load(data)
        missing_MW = series_MW[series_MW['Residual'] > 0]
        overflowing_MW = series_MW[series_MW['Residual'] < 0]

        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column), colspan=size, rowspan=size)

        ax.plot(missing_MW['Index'], missing_MW['Residual'] / 1000, color="darkred")
        ax.fill_between(missing_MW['Index'], missing_MW['Residual'] /
                        1000, color="darkred", alpha=0.3)
        ax.plot(overflowing_MW['Index'], overflowing_MW['Residual'] / 1000, color="darkgreen")
        ax.fill_between(overflowing_MW['Index'],
                        overflowing_MW['Residual'] / 1000, color="darkgreen", alpha=0.3)

        avg_nuclear_hydro_gw = (data["Nuclear"] + data["Hydro"]).mean() / 1000
        ax.axhline(y=avg_nuclear_hydro_gw, color='black')

        shortage_TWh = missing_MW['Residual'].sum() / 1000000
        curtailment_TWh = overflowing_MW['Residual'].sum() / 1000000
        if size == 2:
            label = "Residual: " + self._get_twh_string(shortage_TWh)
            label += " / overflow: " + self._get_twh_string(curtailment_TWh)
        plt.title(label, fontsize=14)
        plt.grid(True)
        plt.box(False)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        # ax.xaxis.set_major_formatter(mtick.PercentFormatter(year_hours))
        ax.set_xticks(list(map(lambda x: 1000 * x, range(0, 11))))
        ax.set_xlim(0, series_MW.shape[0])
        ax.set_xlabel("hours")
        ax.set_ylabel("residual load [GW]")

    def _print_gap_distribution(self,
                                data: pd.DataFrame,
                                label: str,
                                row: int,
                                column: int,
                                size: int = 2) -> None:
        series = data / 1000
        year_hours = series.shape[0]
        series["Index"] = range(0, year_hours)

        missing_MW = series[series['Residual'] > 0]
        # Don't print if there was never a gap.
        if (len(missing_MW.index) == 0):
            return

        state = {"last_id": None, "group": 0}

        def compute_group_ids(state):
            def inner(x):
                if state["last_id"] != None and state["last_id"] + 1 < x["Index"]:
                    state["group"] = state["group"] + 1
                state["last_id"] = x["Index"]
                return pd.Series([state["group"], 1, x['Residual']],
                                 index=['Group', 'Length', 'Residual'])
            # Capture state dictionary to be reused across multiple calls to inner.
            return inner

        annotated = missing_MW.apply(compute_group_ids(state), axis=1, result_type='expand')

        grouped = annotated.groupby(["Group"]).sum().sort_values(by=["Length"])
        groups = grouped.shape[0]
        # Don't print if the whole year is one gap.
        if (groups == 1):
            return

        grouped["Index"] = np.arange(groups)

        to24 = grouped[grouped["Length"] <= 24]
        above_week = grouped[grouped["Length"] > 24*7]

        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column), colspan=size, rowspan=size)

        ax.plot(grouped['Index'], grouped['Length'], color="orange")
        ax.fill_between(grouped['Index'], grouped['Length'], alpha=0.3, color="orange")
        ax.plot(to24['Index'], to24['Length'], color="green")
        ax.fill_between(to24['Index'], to24['Length'], alpha=0.3, color="green")
        ax.plot(above_week['Index'], above_week['Length'], color="red")
        ax.fill_between(above_week['Index'], above_week['Length'], alpha=0.3, color="red")
        if size == 2:
            label = "Gaps in residual by length [hour]"
        plt.title(label, fontsize=14)
        plt.grid(True)
        plt.box(False)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        ax.xaxis.set_major_formatter(mtick.PercentFormatter(groups - 1))
        if size == 2:
            ax.set_xticks(np.floor(np.linspace(0, groups - 1, num=11)))
        ax.set_xlim(0, groups - 1)
        ax.set_xlabel(f"{groups} gaps")

        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(mtick.ScalarFormatter())
        ax.set_ylabel("gap length [hours]")

    def _print_merit_order(self,
                           flexible_sources: dict[FlexibleSourceType, FlexibleSource],
                           row: int,
                           column: int,
                           size: int = 2) -> None:
        # Trim the y-axis to a slightly arbitrary but reasonable value.
        max_price = 250

        merit_order = pd.DataFrame(
            {
                "source": source.type.value,
                "capacity_gw": source.capacity_mw / 1000,
                "price": source.economics.variable_costs_per_mwh_eur,
                "color": source.color,
            }
            for source in flexible_sources.values()
            # Skip ENS and sources with less than 1 kW of installed capacity.
            if source.type != FlexibleSourceType.LOSS_OF_LOAD and source.capacity_mw >= 1e-3
        )
        # Order by ascending marginal costs.
        merit_order.sort_values(by="price", ignore_index=True, inplace=True)
        merit_order["x"] = merit_order["capacity_gw"].shift().fillna(0).cumsum()

        ax = plt.subplot2grid(
            (self._get_plot_params()["rows_stats"], YearlyPlot.columns_stats),
            (row, column), colspan=size, rowspan=size
        )

        ax.bar(
            x=merit_order["x"],
            height=merit_order["price"],
            width=merit_order["capacity_gw"],
            align="edge",
            edgecolor="white",
            color=merit_order["color"],
        )

        for _, source in merit_order.iterrows():
            # Price label above the bar.
            ax.text(
                x=source["x"] + source["capacity_gw"] / 2,
                # Place the label inside the plot area if the price is too high.
                y=min(.95 * max_price, source["price"]),
                s=f"{source['price']:.1f}",
                color="white" if source["price"] >= max_price else source["color"],
                ha="center",
                va="bottom",
                size=6,
            )
            # Source type inside the bar.
            ax.text(
                x=source["x"] + source["capacity_gw"] / 2,
                # Place the label inside the plot area if the price is too high.
                y=min(.85 * max_price, source["price"] / 2),
                s=source["source"],
                color="white",
                ha="center",
                va="bottom",
                size=6,
            )

        plt.title("Merit order", fontsize=14)
        plt.grid(axis="y")
        plt.box(False)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        ax.set_xlabel("Capacity [GWe]")
        ax.set_ylabel("Marginal price [€/MWhe]")
        ax.set_xlim(0, merit_order["capacity_gw"].sum())
        ax.set_ylim(top=max_price)

    def _print_source_distribution(self,
                                   stats: CountryGridStats,
                                   season: Season,
                                   source: Source,
                                   row: int,
                                   column: int,
                                   larger: bool = False) -> None:
        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column))

        values = []
        labels = []
        colors = []

        def add_if_not_zero(stat: StatType, label: str, alpha: float):
            value = stats.get_stat_value(source, stat, season)
            if value == 0:
                return
            values.append(value)
            labels.append(label)
            colors.append(matplotlib.colors.to_rgba(source.color, alpha))

        add_if_not_zero(StatType.POWER_SHARE_ZERO_VALUE, "~zero", 0.25)
        add_if_not_zero(StatType.POWER_SHARE_LOW_VALUE, "low", 0.75)
        add_if_not_zero(StatType.POWER_SHARE_HIGH_VALUE, "high", 1.0)

        if larger:
            label = f"{source.type.value} market price"
        else:
            assert season != Season.YEAR
            label = "winter" if season == Season.WINTER else "summer"
        radius = 1.1 if larger else 0.8

        ax.pie(values, labels=labels, colors=colors, autopct='%.0f%%', startangle=90, radius=radius)
        plt.title(label, fontsize=14)
        plt.box(False)

    def _print_capacity_factors(self,
                                grid: CountryGrid,
                                data: pd.DataFrame, row: int, column: int, label: str) -> None:
        indices = []
        values = []
        colors = []
        labels = []

        total_hours = len(data.index)
        all_sources_mwh = 0
        all_sources_mw = 0

        def add(total_mwh: float, installed_mw: float, color: str, type: str, is_generation=True):
            if total_mwh == 0:
                return
            capacity_factor = total_mwh / (installed_mw * total_hours)
            indices.append(len(values))
            values.append(capacity_factor * 100)
            colors.append(color)
            labels.append(type)
            if is_generation:
                nonlocal all_sources_mwh, all_sources_mw
                all_sources_mwh += total_mwh
                all_sources_mw += installed_mw

        def add_storage(storage_list: Iterable[Storage]):
            for storage in storage_list:
                if (storage.capacity_mw_charging > 0 and storage.separate_charging) or \
                        storage.use == StorageUse.POWER_TO_HEAT:
                    total_mwh_charging = data[get_charging_key(storage)].sum()
                    add(total_mwh_charging, storage.capacity_mw_charging,
                        storage.color, storage.type.value + "+", is_generation=False)

                if storage.capacity_mw > 0:
                    total_mwh_discharging = data[get_discharging_key(
                        storage)].sum()
                    add(total_mwh_discharging, storage.capacity_mw, storage.color,
                        storage.type.value + "-")

        for type, basic_source in grid.basic_sources.items():
            if basic_source.capacity_mw > 0:
                total_mwh = data[get_basic_key(type)].sum()
                add(total_mwh, basic_source.capacity_mw, basic_source.color, basic_source.type.value)

        add_storage(
            storage for storage in grid.storage.values()
            if storage.use in (StorageUse.ELECTRICITY_AS_BASIC, StorageUse.POWER_TO_HEAT)
        )

        # TODO: Use the value from grid stats rather than recomputing it again.
        for flexible_source in grid.flexible_sources.values():
            if flexible_source.capacity_mw > 0 and not flexible_source.virtual:
                key = get_flexible_key(flexible_source)
                # In case of CHP, calculate the capacity factor from
                # total production, including heat (in equivalent
                # electricity).
                if flexible_source.heat:
                    key = get_flexible_electricity_equivalent_key(flexible_source)
                total_mwh = data[key].sum()
                key = get_flexible_key(flexible_source)
                # In case of CHP, calculate the capacity factor from
                # total production, including heat (in equivalent
                # electricity).
                if flexible_source.heat:
                    key = get_flexible_electricity_equivalent_key(flexible_source)
                total_mwh = data[key].sum()
                add(total_mwh, flexible_source.capacity_mw,
                    flexible_source.color, flexible_source.type.value)

        add_storage([storage for storage in grid.storage.values()
                     if storage.use == StorageUse.ELECTRICITY])

        if all_sources_mw == 0:
            return

        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column + 1), colspan=4)

        p = ax.bar(indices, values, color=colors)
        ax.bar_label(p, fmt="%.1f%%")
        plt.xticks(indices, labels, rotation=30)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        plt.title(label, fontsize=14)
        plt.box(False)

        avg_capacity_factor_pct = (all_sources_mwh / (all_sources_mw * total_hours)) * 100
        self._print_label(row, column, "Ø capacity factor",
                          "{:.1f}%".format(avg_capacity_factor_pct), "black")

    def _print_consumer_prices(self,
                               grid: CountryGrid,
                               stats: CountryGridStats,
                               row: int,
                               column: int,
                               title: str) -> None:
        graph_price_per_mwh = YearlyGridPlot.PriceGraphData(average_per_mwh=True)

        chargeable_storages = (
            storage for storage in grid.storage.values()
            if storage.use in (StorageUse.ELECTRICITY, StorageUse.POWER_TO_HEAT)
            and storage.capacity_mw_charging > 0
        )
        # Calculate average buying price for each relevant storage type.
        for storage in chargeable_storages:
            total_twh_charged = stats.get_stat_value(storage, StatType.CHARGED_TWH)
            # Skip sources with negligible charging.
            if total_twh_charged < GENERATION_DISPLAY_THRESHOLD_TWH:
                continue

            charging_key = get_charging_key(storage)
            price_per_mwh = np.average(grid.data[Keys.PRICE], weights=grid.data[charging_key])
            graph_price_per_mwh.add(price_per_mwh, 0, storage.color,
                                    storage.type.value, weight=total_twh_charged)

        # Show average export price for regions with non-negligible
        # total only. Don't show it in the whole-grid plot.
        export_total_twh = stats.get_stat_value(CountryGridStats.total, StatType.EXPORT_TWH)
        if export_total_twh > GENERATION_DISPLAY_THRESHOLD_TWH and not grid.is_complete:
            price_per_mwh = np.average(grid.data[Keys.PRICE], weights=grid.data[Keys.EXPORT])
            graph_price_per_mwh.add(price_per_mwh, 0, ColorMap.INTERCONNECTORS,
                                    "export", weight=export_total_twh)

        # Show average consumer price.
        demand_total_twh = stats.get_stat_value(CountryGridStats.total, StatType.LOAD_TWH)
        price_per_mwh = np.average(grid.data[Keys.PRICE], weights=grid.data[Keys.LOAD])
        graph_price_per_mwh.add(price_per_mwh, 0, "black", "load", weight=demand_total_twh)

        graph_price_per_mwh.print_graph(self, row, column - 1, fmt="%.1f", ylim=500, title=title,
                                        colspan=3, print_label=False)

    def _print_import(self,
                      stats: CountryGridStats,
                      row: int,
                      column: int) -> None:
        total_export_twh = stats.get_stat_value(
            CountryGridStats.total, StatType.EXPORT_TWH)
        total_import_twh = stats.get_stat_value(
            CountryGridStats.total, StatType.IMPORT_TWH)

        label = f"{total_import_twh:.1f} / {total_export_twh:.1f}"
        self._print_label(row, column, "Import / export [TWh]", label, "grey", scale=0.5)

    def _print_installed_capacities(self,
                                    grid: CountryGrid,
                                    row: int,
                                    column: int,
                                    label: str) -> None:
        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column + 1), colspan=4)
        indices = []
        values = []
        colors = []
        labels = []
        total_generation_gw = 0

        def add(capacity_mw: float, color: str, type: str, is_generation=True):
            if capacity_mw == 0:
                return
            capacity_gw = capacity_mw / 1000
            indices.append(len(values))
            values.append(capacity_gw)
            colors.append(color)
            labels.append(type)
            if is_generation:
                nonlocal total_generation_gw
                total_generation_gw += capacity_gw

        def add_storage(storage_list: Iterable[Storage]):
            for storage in storage_list:
                if storage.separate_charging or storage.use == StorageUse.POWER_TO_HEAT:
                    add(storage.capacity_mw_charging,
                        storage.color, storage.type.value + "+", is_generation=False)
                add(storage.capacity_mw,
                    storage.color, storage.type.value + "-")

        for source in grid.basic_sources.values():
            add(source.capacity_mw, source.color, source.type.value)

        add_storage(
            storage for storage in grid.storage.values()
            if storage.use in (StorageUse.ELECTRICITY_AS_BASIC, StorageUse.POWER_TO_HEAT)
        )

        for flexible_source in grid.flexible_sources.values():
            if not flexible_source.virtual:
                add(flexible_source.capacity_mw, flexible_source.color, flexible_source.type.value)

        add_storage(
            storage for storage in grid.storage.values() if storage.use == StorageUse.ELECTRICITY
        )

        p = ax.bar(indices, values, color=colors)
        ax.bar_label(p, fmt="%.1f")
        plt.xticks(indices, labels, rotation=30)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        plt.title(label, fontsize=14)
        plt.box(False)
        self._print_label(row, column, "production capacity",
                          "{:.2f} GW".format(total_generation_gw), "black")

    def _print_production(self,
                          stats: CountryGridStats,
                          row: int,
                          column: int,
                          label: str) -> None:
        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column + 1), colspan=4)
        indices = []
        values = []
        colors = []
        labels = []
        total_production_twh = 0

        def add(production_twh: float, color: str, type: str):
            if production_twh == 0:
                return
            indices.append(len(values))
            values.append(production_twh)
            colors.append(color)
            labels.append(type)
            nonlocal total_production_twh
            total_production_twh += production_twh

        def add_storage(storage_list: list[Storage]):
            for storage_type in storage_list:
                total_twh_discharging = stats.get_stat_value(storage_type, StatType.PRODUCTION_TWH)
                # Skip sources with negligible generation.
                if total_twh_discharging < GENERATION_DISPLAY_THRESHOLD_TWH:
                    continue
                add(total_twh_discharging, storage_type.color, storage_type.type.value + "-")

        for source in stats.grid.basic_sources.values():
            total_twh = stats.get_stat_value(source, StatType.PRODUCTION_TWH)
            # Skip sources with negligible generation.
            if total_twh < GENERATION_DISPLAY_THRESHOLD_TWH:
                continue
            add(total_twh, source.color, source.type.value)

        add_storage([storage for storage in stats.grid.storage.values()
                     if storage.use == StorageUse.ELECTRICITY_AS_BASIC])

        for flexible_source in stats.grid.flexible_sources.values():
            total_twh = stats.get_stat_value(flexible_source, StatType.PRODUCTION_TWH)
            # Skip sources with negligible generation.
            if total_twh < GENERATION_DISPLAY_THRESHOLD_TWH \
                    and flexible_source.type is not FlexibleSourceType.LOSS_OF_LOAD:
                continue
            add(total_twh, flexible_source.color, flexible_source.type.value)

        add_storage([storage for storage in stats.grid.storage.values()
                     if storage.use == StorageUse.ELECTRICITY])

        p = ax.bar(indices, values, color=colors)
        ax.bar_label(p, fmt="%.2f")
        plt.xticks(indices, labels, rotation=30)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        plt.title(label, fontsize=14)
        plt.box(False)
        self._print_label(row, column, "total production",
                          "{:.2f} TWh".format(total_production_twh), "black")

    def _print_heat_production(self,
                               grid: CountryGrid,
                               data: pd.DataFrame,
                               row: int,
                               column: int,
                               label: str) -> None:
        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column + 1))
        indices = []
        values = []
        colors = []
        labels = []
        total_pj = 0

        def add(production_mwh: float, color: str, type: str):
            if production_mwh < GENERATION_DISPLAY_THRESHOLD_MWH:
                return
            production_pj = production_mwh / 1_000_000 * 3.6
            indices.append(len(values))
            values.append(production_pj)
            colors.append(color)
            labels.append(type)
            nonlocal total_pj
            total_pj += production_pj

        for flexible_source in grid.flexible_sources.values():
            if flexible_source.heat:
                key = get_flexible_heat_key(flexible_source)
                add(data[key].sum(), flexible_source.color, flexible_source.type.value)

        for storage in grid.storage.values():
            if storage.use == StorageUse.POWER_TO_HEAT:
                key = get_p2h_heat_key(storage)
                add(data[key].sum(), storage.color, storage.type.value)

        p = ax.bar(indices, values, color=colors)
        ax.bar_label(p, fmt="%.1f")
        plt.xticks(indices, labels, rotation=30)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        plt.title(label, fontsize=14)
        plt.box(False)
        self._print_label(row, column, "total heat production",
                          "{:.2f} PJ".format(total_pj), "black")

    def _print_prices(self,
                      grid: CountryGrid,
                      stats: CountryGridStats,
                      first_row: int,
                      column: int,
                      title_cost_total: str,
                      title_cost_per_mwh: str,
                      title_price_per_mwh: str) -> None:
        # Prices in bil. EUR.
        graph_costs_total = YearlyGridPlot.PriceGraphData()
        # Costs in EUR.
        graph_costs_per_mwh = YearlyGridPlot.PriceGraphData(average_per_mwh=True)
        # Prices in EUR.
        graph_price_per_mwh = YearlyGridPlot.PriceGraphData(average_per_mwh=True)

        def add_storage(storage_list: list[Storage]):
            for storage in storage_list:
                capex_mn_eur = stats.get_stat_value(storage, StatType.CAPEX_MN_EUR_PER_YEAR)
                opex_mn_eur = stats.get_stat_value(storage, StatType.OPEX_MN_EUR)
                # Total cost. Includes all the capex and opex costs, excluding cost for buying
                # electricity as this is counted in production system costs (and with no adjustments
                # for internal "consumption" like in cost-per-MWh below). Ignore negligible costs
                # (below thousand EUR).
                if capex_mn_eur + opex_mn_eur > 1e-3:
                    graph_costs_total.add(capex_mn_eur / 1e3, opex_mn_eur / 1e3,
                                          storage.color, storage.type.value)

                # Average price per sold MWh.
                total_twh_discharged = stats.get_stat_value(storage, StatType.DISCHARGED_TWH)
                # Skip sources with negligible generation.
                if total_twh_discharged > GENERATION_DISPLAY_THRESHOLD_TWH:
                    sell_price_mn_eur = stats.get_stat_value(
                        storage, StatType.WHOLESALE_REVENUES_MN_EUR)
                    price_per_mwh = sell_price_mn_eur / total_twh_discharged
                    graph_price_per_mwh.add(price_per_mwh, 0, storage.color,
                                            storage.type.value, weight=total_twh_discharged)

                # Cost-per-MWh can be inflated by internal consumption. This means charging a lot of
                # electricity with no or little discharging because all the charge gets consumed
                # internally (BEVs) or sold directly (H2). In this case, average cost per discharged
                # MWh could get insanely high. Adjust for this effect.
                total_twh_discharged_or_sold: float = total_twh_discharged
                consumption_twh = (storage.final_energy_mwh - storage.initial_energy_mwh) / 1e6
                if consumption_twh > 0:
                    # Recompute internal "consumption" (such as selling H2) as if it was discharged
                    # (and add corresponding virtual discharging opex).
                    sold_as_if_discharged_twh = consumption_twh * storage.discharging_efficiency
                    total_twh_discharged_or_sold += sold_as_if_discharged_twh
                    opex_mn_eur += sold_as_if_discharged_twh * storage.economics.variable_costs_per_mwh_eur

                # For cost per MWh, remove part of production that corresponds to paid off capacity.
                if storage.capacity_mw > 0 and storage.paid_off_capacity_mw > 0:
                    newly_built_ratio = 1 - (storage.paid_off_capacity_mw / storage.capacity_mw)
                    total_twh_discharged_or_sold *= newly_built_ratio
                    opex_mn_eur *= newly_built_ratio
                if total_twh_discharged_or_sold > 0:
                    capex_per_mwh = capex_mn_eur / total_twh_discharged_or_sold
                    discharging_opex_per_mwh = opex_mn_eur / total_twh_discharged_or_sold
                    # TODO: Consider showing StatType.WHOLESALE_EXPENSES_MN_EUR as well (i.e.
                    # electricity buying costs), ideally separately from OPEX to make it clearer
                    # this aspect is included.
                    graph_costs_per_mwh.add(capex_per_mwh, discharging_opex_per_mwh,
                                            storage.color, storage.type.value,
                                            weight=total_twh_discharged)

        for source in grid.basic_sources.values():
            if source.capacity_mw > 0:
                total_twh = stats.get_stat_value(source, StatType.PRODUCTION_TWH)
                # Skip sources with negligible generation.
                if total_twh < GENERATION_DISPLAY_THRESHOLD_TWH:
                    continue

                capex_mn_eur = stats.get_stat_value(source, StatType.CAPEX_MN_EUR_PER_YEAR)
                opex_mn_eur = stats.get_stat_value(source, StatType.OPEX_MN_EUR)
                total_price_mn_eur = stats.get_stat_value(
                    source, StatType.WHOLESALE_REVENUES_MN_EUR)

                graph_costs_total.add(capex_mn_eur / 1e3, opex_mn_eur / 1e3,
                                      source.color, source.type.value)
                price_per_mwh = total_price_mn_eur / total_twh
                graph_price_per_mwh.add(price_per_mwh, 0, source.color,
                                        source.type.value, weight=total_twh)

                # For cost per MWh, remove part of production that corresponds to paid off capacity.
                if source.paid_off_capacity_mw > 0:
                    newly_built_ratio = 1 - (source.paid_off_capacity_mw / source.capacity_mw)
                    total_twh *= newly_built_ratio
                    opex_mn_eur *= newly_built_ratio
                if total_twh > 0:
                    capex_per_mwh = capex_mn_eur / total_twh
                    opex_per_mwh = opex_mn_eur / total_twh
                    graph_costs_per_mwh.add(capex_per_mwh, opex_per_mwh, source.color,
                                            source.type.value, weight=total_twh)

        add_storage([storage for storage in grid.storage.values()
                     if storage.use == StorageUse.ELECTRICITY_AS_BASIC])

        for flexible_source in grid.flexible_sources.values():
            if not flexible_source.virtual:
                total_twh = stats.get_stat_value(flexible_source, StatType.PRODUCTION_TWH)
                # Skip sources with negligible generation.
                if total_twh < GENERATION_DISPLAY_THRESHOLD_TWH:
                    continue

                capex_mn_eur = stats.get_stat_value(flexible_source, StatType.CAPEX_MN_EUR_PER_YEAR)
                opex_mn_eur = stats.get_stat_value(flexible_source, StatType.OPEX_MN_EUR)
                total_price_mn_eur = stats.get_stat_value(flexible_source,
                                                          StatType.WHOLESALE_REVENUES_MN_EUR)

                graph_costs_total.add(capex_mn_eur / 1e3, opex_mn_eur / 1e3,
                                      flexible_source.color, flexible_source.type.value)
                price_per_mwh = total_price_mn_eur / total_twh
                graph_price_per_mwh.add(price_per_mwh, 0, flexible_source.color,
                                        flexible_source.type.value, weight=total_twh)

                # For cost per MWh, remove part of production that corresponds to paid off capacity.
                if flexible_source.capacity_mw > 0 and flexible_source.paid_off_capacity_mw > 0:
                    newly_built_ratio = 1 - (flexible_source.paid_off_capacity_mw /
                                             flexible_source.capacity_mw)
                    total_twh *= newly_built_ratio
                    opex_mn_eur *= newly_built_ratio
                if total_twh > 0:
                    capex_per_mwh = capex_mn_eur / total_twh
                    opex_per_mwh = opex_mn_eur / total_twh
                    graph_costs_per_mwh.add(capex_per_mwh, opex_per_mwh, flexible_source.color,
                                            flexible_source.type.value, weight=total_twh)

        add_storage([storage for storage in grid.storage.values()
                    if storage.use == StorageUse.ELECTRICITY])

        import_total_twh = stats.get_stat_value(CountryGridStats.total, StatType.IMPORT_TWH)
        # Show average import price for regions with non-negligible
        # total only. Don't show it in the whole-grid plot.
        if import_total_twh > GENERATION_DISPLAY_THRESHOLD_TWH and not grid.is_complete:
            price_per_mwh = np.average(grid.data[Keys.PRICE], weights=grid.data[Keys.IMPORT])
            graph_price_per_mwh.add(price_per_mwh, 0, ColorMap.INTERCONNECTORS,
                                    "import", weight=import_total_twh)

        interconnector_capex = stats.get_stat_value_if_exists(CountryGridStats.import_export,
                                                              StatType.CAPEX_MN_EUR_PER_YEAR)
        if interconnector_capex is not None and interconnector_capex > 0:
            graph_costs_total.add(0, interconnector_capex / 1e3,
                                  ColorMap.INTERCONNECTORS, "interconnectors")

        graph_costs_total.print_graph(self, first_row, column, "%.2f", None, title_cost_total)
        graph_costs_per_mwh.print_graph(self, first_row + 1, column,
                                        "%.1f", 500, title_cost_per_mwh)
        graph_price_per_mwh.print_graph(self, first_row + 2, column,
                                        "%.1f", 500, title_price_per_mwh)

    def _print_storage(self,
                       grid: CountryGrid,
                       data: pd.DataFrame,
                       stats: CountryGridStats,
                       row: int,
                       column: int,
                       label: str) -> None:
        """
        Plot summary and bars for grid storage and curtailment.
        """
        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column + 1), colspan=3)
        indices = []
        discharging = []
        charging = []
        colors = []
        labels = []

        sum_discharging_twh = 0
        sum_charging_twh = 0

        def add(discharging_twh: float, charging_twh: float, color: str, type: str, virtual=False):
            indices.append(len(indices))
            discharging.append(discharging_twh)
            # Force the value to be negative to push the label down the bar. This is useful for
            # storage types with no charging.
            charging.append(-1 * charging_twh)
            colors.append(color)
            labels.append(type)
            if not virtual:
                nonlocal sum_discharging_twh, sum_charging_twh
                sum_discharging_twh += discharging_twh
                sum_charging_twh += charging_twh

        for storage in grid.storage.values():
            total_discharging_twh = stats.get_stat_value(storage, StatType.DISCHARGED_TWH)
            total_charging_twh = stats.get_stat_value(storage, StatType.CHARGED_TWH)
            add(total_discharging_twh, total_charging_twh,
                storage.color, storage.type.value)

        total_curtailment_twh = stats.get_stat_value(CountryGridStats.total,
                                                     StatType.CURTAILMENT_TWH)
        add(0, total_curtailment_twh, "gray", "curtail", virtual=True)

        # Only print bars and bar labels for values that are non-zero, i.e.
        # don't print "0.00" is the type has no discharging at all.
        p1 = ax.bar(
            [i for i in indices if discharging[i] > 0],
            [y for y in discharging if y > 0],
            color=[c for i, c in enumerate(colors) if discharging[i] > 0]
        )
        p2 = ax.bar(
            [i for i in indices if charging[i] < 0],
            [y for y in charging if y < 0],
            color=[c for i, c in enumerate(colors) if charging[i] < 0],
            alpha=self._get_alpha_negative()
        )
        ax.bar_label(p1, fmt="%.2f")
        ax.bar_label(p2, fmt="%.2f")
        ax.axhline(color="black", lw=0.5)
        plt.xticks(indices, labels, rotation=30)
        ax.margins(y=0.25)  # Make space for the ticks and labels
        plt.title(label, fontsize=14)
        plt.box(False)
        # Show storage sum only if there are storage facilities
        # in the grid.
        if grid.storage:
            self._print_label(row, column, "Σ discharged",
                              "{:.2f} TWh".format(sum_discharging_twh), ColorMap.STORAGE,
                              subtitle="out of {:.2f} TWh charged".format(sum_charging_twh))

    def _print_emissions(self,
                         stats: CountryGridStats,
                         row: int, column: int, label: str) -> None:
        total_co2_emissions_Mt = stats.get_stat_value(
            CountryGridStats.total, StatType.EMISSIONS_MTCO2)
        if total_co2_emissions_Mt == 0:
            return

        emissions_mtco2_all: list[StatPlotElement] = stats.get_stat_plot_elements(
            StatType.EMISSIONS_MTCO2)
        emissions_mtco2 = [stat for stat in emissions_mtco2_all if stat.value != 0.0]
        indices = range(len(emissions_mtco2))
        values = [stat.value for stat in emissions_mtco2]
        colors = [stat.color for stat in emissions_mtco2]
        labels = [stat.label for stat in emissions_mtco2]

        self._print_label(row, column, "CO2 emissions [Mt]", "{:.1f} Mt".format(
            total_co2_emissions_Mt), "black")

        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column + 1))
        p1 = ax.bar(indices, values, color=colors)
        ax.bar_label(p1, fmt="%.1f")
        plt.xticks(indices, labels, rotation=30)
        plt.box(False)

    def _print_res_share(
            self, grid: CountryGrid, data: pd.DataFrame, row: int, column: int) -> None:
        load_twh = data[Keys.LOAD].sum() / 1_000_000
        if load_twh == 0:
            return

        res_production_twh: float = 0
        indices: list[int] = []
        values: list[float] = []
        colors: list[str] = []
        labels: list[str] = []

        def add(source: Source, series):
            production_twh = series.sum() / 1_000_000
            if not source.virtual and source.renewable \
                    and production_twh > GENERATION_DISPLAY_THRESHOLD_TWH:
                nonlocal res_production_twh
                res_production_twh += production_twh
                indices.append(len(indices))
                values.append(production_twh)
                colors.append(source.color)
                labels.append(source.type.value)

        for type in grid.basic_sources.keys():
            if get_basic_used_key(type) in data:
                key = get_basic_used_key(type)
            else:
                key = get_basic_key(type)
            add(grid.basic_sources[type], data[key])
        for flexible_source in grid.flexible_sources.values():
            add(flexible_source, data[get_flexible_key(flexible_source)])
        for storage in grid.storage.values():
            if storage.use.is_electricity():
                discharging_key = get_discharging_key(storage)
                charging_key = get_charging_key(storage)
                add(storage, data[discharging_key] - data[charging_key])

        res_share_pct = (res_production_twh / load_twh) * 100
        self._print_label(row, column, "RES share", "{:.1f}%".format(res_share_pct),
                          "black", 1, "{:.1f} TWh".format(res_production_twh))

        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column + 1), colspan=3)
        p1 = ax.bar(indices, values, color=colors)
        ax.bar_label(p1, fmt="%.2f TWh")
        ax.bar_label(p1, labels=["%.1f%%" % ((twh / load_twh) * 100) for twh in values], padding=12)
        plt.xticks(indices, labels)
        plt.box(False)

    def _print_label(self,
                     row: int,
                     column: int,
                     title: str,
                     label: str,
                     color: str,
                     scale: float = 1.0,
                     subtitle: Optional[str] = None,
                     margins: float = -0.2) -> None:
        ax = plt.subplot2grid((self._get_plot_params()['rows_stats'], YearlyPlot.columns_stats),
                              (row, column))
        title_size = max(14 * scale, 10)
        value_size = max(32 * scale, 16)
        ax.set_axis_off()

        ax.text(0.5, 1 - margins, title, size=title_size, ha='center', va='top', clip_on=False)
        if subtitle is not None:
            ypos = 0.5
            ax.text(0.5, margins, subtitle, size=title_size,
                    ha='center', va='bottom', clip_on=False)
        else:
            ypos = 0.45

        ax.text(0.5, ypos, label, size=value_size, ha='center',
                va='center', color=color, clip_on=False)

    def _plot_additional_graphs(self, region: Region, data: pd.DataFrame) -> None:
        stats = self.stats[region]
        grid = stats.grid

        mean_total_gw = data["Production"].mean() / 1000
        # Add a safety margin of 30% to account for seasonal variability.
        season_max_twh = mean_total_gw * \
            self._get_plot_params()['ylim_factor'] * 24 * (365/2) / 1000 * 1.3

        # Make sure the 0 line gets plotted.
        season_min_twh = -1
        factor_season = self._get_plot_params()['ylim_factor'] * 24 * (365/2) / 1000
        mean_export_gw = data["Export"].mean() / 1000
        season_min_twh -= mean_export_gw * factor_season
        if 'Charging' in data.columns:
            mean_charging_gw = data["Charging"].mean() / 1000
            season_min_twh -= mean_charging_gw * factor_season

        summer_slice = get_summer_slice(data)
        winter_slice = get_winter_slice(data)

        self._print_installed_capacities(
            grid, row=0, column=0, label="Installed capacity [GW]")

        self._print_production(stats, row=1, column=0, label="Production [TWh]")

        show_storage_block = (
            len(grid.storage) > 0 or
            (data["Curtailment"] > 1e-3).any()
        )
        if show_storage_block:
            self._print_storage(grid, data, stats, row=2, column=0,
                                label="Discharging / -Charging [TWh]")

        show_import_balance = not grid.is_complete
        if show_import_balance:
            self._print_import(stats, row=2, column=4)

        if grid.flexible_sources or grid.storage:
            self._print_capacity_factors(grid, data, row=3, column=0, label="Capacity factors")

        self._print_res_share(grid, data, row=4, column=0)

        self._print_prices(grid, stats, first_row=5, column=0,
                           title_cost_total="system costs",
                           title_cost_per_mwh="system cost",
                           title_price_per_mwh="producer price")

        self._print_consumer_prices(grid, stats, row=7, column=5, title="consumer price")

        if grid.flexible_sources:
            self._print_emissions(stats, row=0, column=5, label="CO₂ emissions [Mt]")

        if Keys.HEAT_FLEXIBLE_PRODUCTION in data or Keys.HEAT_P2H_PRODUCTION in data:
            self._print_heat_production(
                grid, data, row=1, column=5, label="Heat production [PJ]")

        self._print_residual_load(data, "", row=2, column=5)
        # self._print_residual_load(summer_slice, "Summer", row=4, column=4, size=1)
        # self._print_residual_load(winter_slice, "Winter", row=4, column=5, size=1)

        # self._print_gap_distribution(data, "", row=5, column=4)
        # self._print_gap_distribution(summer_slice, "Summer", row=7, column=4, size=1)
        # self._print_gap_distribution(winter_slice, "Winter", row=7, column=5, size=1)

        if grid.flexible_sources:
            self._print_merit_order(grid.flexible_sources, row=4, column=5)

        if BasicSourceType.SOLAR in grid.basic_sources:
            solar = grid.basic_sources[BasicSourceType.SOLAR]
            self._print_source_distribution(stats, Season.YEAR, solar, row=0, column=7, larger=True)
            self._print_source_distribution(stats, Season.SUMMER, solar, row=1, column=7)
            self._print_source_distribution(stats, Season.WINTER, solar, row=2, column=7)

        # TODO: replace by WIND.
        if BasicSourceType.ONSHORE in grid.basic_sources:
            wind = grid.basic_sources[BasicSourceType.ONSHORE]
            self._print_source_distribution(stats, Season.YEAR, wind, row=3, column=7, larger=True)
            self._print_source_distribution(stats, Season.SUMMER, wind, row=4, column=7)
            self._print_source_distribution(stats, Season.WINTER, wind, row=5, column=7)

        if BasicSourceType.NUCLEAR in grid.basic_sources:
            nuclear = grid.basic_sources[BasicSourceType.NUCLEAR]
            self._print_source_distribution(
                stats, Season.YEAR, nuclear, row=6, column=7, larger=True)

        rows_stats = self._get_plot_params()['rows_stats']

        # ax = plt.subplot2grid((rows_stats, YearlyPlot.columns_stats), (0, 7), rowspan=2)
        # self._print_summary(ax, region, data, season_min_twh * 2, season_max_twh * 2,
        #                     'electricity', label="Production", weekly=False)
        # ax = plt.subplot2grid((rows_stats, YearlyPlot.columns_stats), (2, 7), rowspan=1)
        # self._print_summary(ax, region, summer_slice, season_min_twh, season_max_twh,
        #                     'electricity', label="Summer", weekly=False)
        # ax = plt.subplot2grid((rows_stats, YearlyPlot.columns_stats), (3, 7), rowspan=1)
        # self._print_summary(ax, region, winter_slice, season_min_twh, season_max_twh,
        #                     'electricity', label="Winter", weekly=False)

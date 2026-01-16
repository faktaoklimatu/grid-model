"""
Plots yearly sensitivity stats into one combined figure.
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick

from .grid_plot_utils import *
from .color_map import ColorMap
from .sensitivity_plot import SensitivityPlot


class SensitivityGridPlot(SensitivityPlot):
    def __init__(self, sensitivity, params_list, df_list, title, subtitle, factors_str, out_filename, name):
        for df in df_list:
            # Modifies data in place.
            grid_plot_utils.split_excess_production(df)

        # Use the first df for expanding the titles.
        sums_twh = df_list[0].sum() / 1000000
        title_expanded = title.format(sums_twh[Keys.LOAD])
        subtitle_expanded = subtitle.format(
            sums_twh['Solar'], sums_twh['Wind'], sums_twh['Nuclear'], sums_twh['Hydro'], sums_twh['Biomass'])
        subtitle_expanded += "\n" + factors_str

        super().__init__(sensitivity, params_list, df_list, title_expanded, subtitle_expanded, out_filename, name)

    def _get_plot_params(self):
        return {'size_x': 6,
                'size_y': 3,
                'rows': 4,
                'columns': 3}

    def _print_balance(self, ax, sensitivity_value, data, params, bar_width):
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
            excess_wind
        ) = grid_plot_utils.get_grid_balance(data, [])

        ax.bar(sensitivity_value, nuclear, color=ColorMap.NUCLEAR, width=bar_width)
        ax.bar(sensitivity_value, hydro, color=ColorMap.HYDRO, width=bar_width, bottom=nuclear)
        ax.bar(sensitivity_value, wind, color=ColorMap.WIND, width=bar_width, bottom=nuclear+hydro)
        ax.bar(sensitivity_value, solar, color=ColorMap.SOLAR,
               width=bar_width, bottom=nuclear+hydro+wind)

        line_range = [sensitivity_value - bar_width/2, sensitivity_value + bar_width/2]
        ax.plot(line_range, [load, load], lw=3, color=ColorMap.LOAD)
        # ax.axhline(color='black', lw=0.5)

        ax.bar(sensitivity_value, excess_wind, color=ColorMap.WIND, width=bar_width, bottom=load)
        ax.bar(sensitivity_value, excess_solar, color=ColorMap.SOLAR,
               width=bar_width, bottom=load+excess_wind)

    def _print_summer_balance(self, ax, sensitivity_value, data, params, bar_width):
        self._print_balance(ax, sensitivity_value,
                            grid_plot_utils.get_summer_slice(data), params, bar_width)

    def _print_winter_balance(self, ax, sensitivity_value, data, params, bar_width):
        self._print_balance(ax, sensitivity_value,
                            grid_plot_utils.get_winter_slice(data), params, bar_width)

    def _print_residual_load(self, ax, sensitivity_value, data, params, bar_width):
        series_MW = grid_plot_utils.get_residual_load(data)
        label = self.sensitivity['param_name'] + ": " + str(sensitivity_value)
        ax.plot(series_MW['Index'], series_MW['Residual'] / 1000, label=label)

    def _print_shortage_surplus(self, ax, sensitivity_value, data, params, bar_width):
        _, curtailment_MW, shortage_MW = grid_plot_utils.get_storable_curtailment_shortage(data)
        curtailment_TWh = curtailment_MW['Storable'].sum() / 1000000
        shortage_TWh = shortage_MW['Storable'].sum() / 1000000

        ax.bar(sensitivity_value, curtailment_TWh, color="darkgreen", width=bar_width)
        ax.bar(sensitivity_value, shortage_TWh, color="darkred", width=bar_width)

    def _print_market(self, ax, sensitivity_value, data, params, bar_width, source, color):
        _, _, shortage_MW = grid_plot_utils.get_storable_curtailment_shortage(data)
        all_generation = data[source].sum()
        high_price_generation = shortage_MW[source].sum()
        ax.bar(sensitivity_value, high_price_generation /
               all_generation, color=color, width=bar_width)

    def _print_solar_market(self, ax, sensitivity_value, data, params, bar_width):
        self._print_market(ax, sensitivity_value, data, params, bar_width, "Solar", ColorMap.SOLAR)

    def _print_wind_market(self, ax, sensitivity_value, data, params, bar_width):
        self._print_market(ax, sensitivity_value, data, params, bar_width, "Wind", ColorMap.WIND)

    def _print_graphs(self, rows, columns):
        ax = plt.subplot2grid((rows, columns), (0, 0), rowspan=2)
        self._print_subgraph(ax, self._print_balance, "Balance: whole year",
                             ylabel="Electricity [TWh]")

        ax = plt.subplot2grid((rows, columns), (0, 1), rowspan=2)
        self._print_subgraph(ax, self._print_summer_balance,
                             "Balance: summer", ylabel="Electricity [TWh]")

        ax = plt.subplot2grid((rows, columns), (0, 2), rowspan=2)
        self._print_subgraph(ax, self._print_winter_balance,
                             "Balance: winter", ylabel="Electricity [TWh]")

        ax = plt.subplot2grid((rows, columns), (2, 0), rowspan=2)
        self._print_subgraph(ax, self._print_residual_load, "Residual load",
                             xlabel="Hours", ylabel="Load [GW]")
        ax.legend()

        ax = plt.subplot2grid((rows, columns), (2, 1), rowspan=2)
        self._print_subgraph(ax, self._print_shortage_surplus,
                             "Surplus (+) / Shortages (-)", ylabel="Electricity [TWh]")

        ax = plt.subplot2grid((rows, columns), (2, 2))
        self._print_subgraph(ax, self._print_solar_market, "Market for solar",
                             ylabel="Valuable solar production [%]")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))

        ax = plt.subplot2grid((rows, columns), (3, 2))
        self._print_subgraph(ax, self._print_wind_market, "Market for wind",
                             ylabel="Valuable wind production [%]")
        ax.yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))

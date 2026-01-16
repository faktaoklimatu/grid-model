"""
Plots yearly sensitivity stats into one combined figure.
"""

import subprocess

import matplotlib.pyplot as plt


class SensitivityPlot:
    def __init__(self, sensitivity, params_list, df_list, title, subtitle, out_filename, name):
        self.sensitivity = sensitivity
        self.params_list = params_list
        self.df_list = df_list
        self.title = title
        self.subtitle = subtitle
        self.out_filename = out_filename
        self.name = name

    def _get_plot_params(self):
        raise NotImplementedError()

    def _print_subgraph(self, ax, print_sensitivity_value_callback, label, xlabel=None, ylabel=None):
        bar_width = self.sensitivity['bar_width']
        for index, sensitivity_value in enumerate(self.sensitivity['values']):
            data = self.df_list[index]
            params = self.params_list[index]
            print_sensitivity_value_callback(ax, sensitivity_value, data, params, bar_width)

        plt.title(label, fontdict={'fontsize': 24})

        if xlabel != None:
            ax.set_xlabel(xlabel)
        else:
            ax.set_xticks(self.sensitivity['values'])
            ax.set_xlabel(self.sensitivity['param_name'])

        if ylabel != None:
            ax.set_ylabel(ylabel)

    def _print_graphs(self, rows, columns):
        raise NotImplementedError()

    def print_graph(self):
        print("Plotting sensitivity graph...", end=" ")
        rows = self._get_plot_params()['rows']
        columns = self._get_plot_params()['columns']
        plt.rcParams['figure.figsize'] = (self._get_plot_params()['size_x'] * columns,
                                          self._get_plot_params()['size_y'] * rows)
        fig = plt.figure()

        self._print_graphs(rows, columns)

        fig.patch.set_facecolor('white')
        fig.suptitle(self.title, size=28, y=max(1.0075, 1.1 - 0.006 * rows))
        plt.figtext(0.5, min(0.9975, 0.97 + 0.001 * rows), self.subtitle, size=18, ha='center')

        fig.tight_layout(h_pad=3, w_pad=3)

        plt.savefig(self.out_filename, bbox_inches='tight', pad_inches=0.2, dpi=300)
        plt.close(fig)
        plt.clf()

        print("Done")

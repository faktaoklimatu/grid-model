"""
Plots yearly stats into one combined figure.
"""

import datetime
import operator as op
from pathlib import Path
from typing import Optional, Sequence, Union

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.container import BarContainer
from PIL import Image

from .logging import get_logger
from .region import Region
from .yearly_filter import YearlyFilter
from .color_map import ColorMap


logger = get_logger(__name__)


def can_arrange(format: str):
    return format == "png" or format == "jpg" or format == "jpeg" or format == "gif"


def arrange_plots(
    input_paths: Sequence[Union[str, Path]],
    output_path: Union[str, Path],
    padding: Optional[float] = 2.5,
    horizontal=False,
) -> None:
    """
    Arrange images in a sequence either vertically (default) or
    side-by-side. The second and further images are scaled
    proportionally so that they match the first image in width or
    height, respectively.

    Arguments:
        input_paths: Paths to input files. At least two images are
            required.
        output_path: Path to the merged output file.
        padding: Amount of padding to add between images and around the
            resulting plot, in percent of the width (or height) of the
            first image. The default is 2.5% between and on each side.
        horizontal: Whether to arrange the images horizontally
            (side-by-side) as opposed to vertically (default).
    """
    if len(input_paths) < 2:
        raise ValueError("Two or more input images expected")
    if padding is not None and padding < 0:
        raise ValueError("Padding amount must be nonnegative")

    get_major = op.attrgetter("width" if horizontal else "height")
    get_minor = op.attrgetter("height" if horizontal else "width")

    # Open all images at once so we can compute the required dimensions.
    images = [Image.open(path) for path in input_paths]

    first_image = images[0]
    # Size of the first image along the minor dimension (orthogonal) to
    # the direction of arranging.
    minor_size = get_minor(first_image)
    scaling_factors = [minor_size / get_minor(im) for im in images]
    scaled_majors = [
        round(factor * get_major(im)) for factor, im in zip(scaling_factors, images)
    ]
    padding_pixels = round(minor_size * padding / 100) if padding else 0

    if horizontal:
        result_height = minor_size + 2 * padding_pixels
        result_width = sum(scaled_majors) + (1 + len(input_paths)) * padding_pixels
    else:
        result_height = sum(scaled_majors) + (1 + len(input_paths)) * padding_pixels
        result_width = minor_size + 2 * padding_pixels

    result = Image.new("RGB", (result_width, result_height))
    result.paste("white", (0, 0, result_width, result_height))

    # Offset from the top/left of the resulting image, i.e. cumulative
    # height/width of preceding images (including padding).
    major_offest = padding_pixels

    # Resize subsequent images to match the first one in size.
    for image, major_size in zip(images, scaled_majors):
        dimensions = (
            (major_size, minor_size) if horizontal else (minor_size, major_size)
        )
        with image.resize(dimensions) as image_resized:
            coordinates = (
                (major_offest, padding_pixels)
                if horizontal
                else (padding_pixels, major_offest)
            )
            result.paste(image_resized, coordinates)
            major_offest += major_size + padding_pixels
        image.close()

    with result:
        result.save(output_path)


class YearlyPlot:
    colspan_day = 4
    colspan_week_summary = 2
    columns_days = 7 * colspan_day + 2
    columns_stats = 8
    min_week = 2
    max_week = 51

    def __init__(
        self,
        data_map: dict[Region, pd.DataFrame],
        year: int,
        yearly_filter: YearlyFilter,
        output: dict,
        out_dir: Path,
        name: str,
    ) -> None:
        self.year = year
        self.output = output
        self.parts = self.output["parts"]
        self.out_dir = out_dir
        self.name = name
        self.weeks = yearly_filter.get_weeks()
        self.days_of_year = yearly_filter.get_days_of_year()
        self.week_height = sum(self._get_plot_params()["week_graphs"].values())
        self.rows = len(self.weeks) * self.week_height
        self.label_even = False
        self.data_map = data_map

        matplotlib.rc("font", family="sans-serif")
        matplotlib.rc("font", serif="Inter")
        matplotlib.rc("text", usetex="false")
        matplotlib.rc("svg", fonttype="none")

    def _get_weekly_data_frame(self, data: pd.DataFrame, week: int) -> pd.DataFrame:
        if self.days_of_year is None:
            return data[
                (data.index.year == self.year) & (data.index.isocalendar().week == week)
            ]
        return data[
            (data.index.year == self.year)
            & (data.index.isocalendar().week == week)
            & (data.index.day_of_year.isin(self.days_of_year))
        ]

    def _get_twh_string(self, number: float) -> str:
        return "{:.2f} TWh".format(number)

    def _with_label(
        self,
        value: float,
        scale: float,
        weekly: bool,
        ax: plt.Axes,
        container: BarContainer,
    ) -> None:
        if weekly and scale == 0:
            value *= 1000
            limit = 0.5
            label = "{x:>3,.0f} GWh".format(x=value)
        elif weekly:
            value = (value / scale) * 100
            limit = 0.5
            label = "{x:>3,.0f} %".format(x=value)
        else:
            limit = 0.05
            label = "{x:>3,.1f} TWh".format(x=value)

        # Don't plot zero labels (that show 0% or 0.0 Twh).
        if -limit <= value <= limit:
            return

        rect = container.patches[0]

        x = rect.get_x()
        margin = -0.02
        ha = "right"
        if self.label_even:
            x += rect.get_width()
            margin *= -1
            ha = "left"
        va = "bottom"
        if value < 0:
            va = "top"
        ax.text(x + margin, rect.get_y(), label, ha=ha, va=va, size=6)
        self.label_even = not self.label_even

    def _annotate_weekly_graph(
        self, ax: plt.Axes, start_date: datetime.date, days: int, type: str
    ) -> None:
        # Always set the range of the plot for the full week, to keep the width of a day constant.
        ax.set_xlim(0, 7 * 24)
        plt.box(False)

        for day in range(1, days):
            ax.axvline(24 * day, color=ColorMap.GRAY, lw=1, ls=":")

        if type == "electricity":
            ax.xaxis.set_ticks([12 + 24 * day for day in range(days)])
            ax.xaxis.set_tick_params(length=0, labeltop=True, labelbottom=False)

            def format_date(x, _):
                date = start_date + datetime.timedelta(hours=x.item())
                if self.output.get("dates_leading_zeroes", True):
                    return date.strftime("%d. %m.")
                else:
                    return date.strftime("%-d. %-m.")

            ax.xaxis.set_major_formatter(format_date)
            ax.tick_params(axis="x", which="major", pad=3)

        else:
            ax.xaxis.set_ticks([])

    def _get_plot_params(self) -> dict:
        raise NotImplementedError()

    def _get_titles(self, region: Region, data: pd.DataFrame) -> tuple[str, str]:
        raise NotImplementedError()

    def _compute_week_ylim(self, type: str, data: pd.DataFrame) -> tuple[float, float]:
        raise NotImplementedError()

    def _compute_summary_ylim(
        self, type: str, data: pd.DataFrame
    ) -> tuple[float, float]:
        raise NotImplementedError()

    def _print_weekly_graph(
        self,
        ax: plt.Axes,
        region: Region,
        weekly_index: list[float],
        weekly_data: pd.DataFrame,
        type: str,
    ) -> None:
        raise NotImplementedError()

    def _print_summary(
        self,
        ax: plt.Axes,
        region: Region,
        data: pd.DataFrame,
        ylim_min: float,
        ylim_max: float,
        type: str,
        label: str,
        weekly: bool,
    ) -> None:
        raise NotImplementedError()

    def _plot_additional_graphs(self, region: Region, data: pd.DataFrame) -> None:
        raise NotImplementedError()

    def _get_plot_filename(self, name: Optional[str] = None) -> Path:
        if name is None:
            return self.out_dir.with_name(
                f"{self.out_dir.name}.{self.output['format']}"
            )
        return self.out_dir / "{}.{}".format(name, self.output["format"])

    def print_graph(self) -> None:
        output_list: list[Path] = []
        for region, data in self.data_map.items():
            logger.info("Plotting yearly graph for {}".format(region))
            region_output_path = self._print_graph(region, data)
            if region_output_path.exists():
                output_list.append(region_output_path)

        aggregate_path = self._get_plot_filename()
        if len(output_list) == 1:
            output_list[0].rename(aggregate_path)
            logger.debug(f"Single country plot moved to {aggregate_path}")
        elif len(output_list) > 1 and can_arrange(self.output["format"]):
            arrange_plots(output_list, aggregate_path, horizontal=True)
            logger.debug(f"Aggregate plot moved to {aggregate_path}")

    def _print_graph(self, region: Region, data: pd.DataFrame) -> Path:
        filename_output: str = region
        output_path = self._get_plot_filename(filename_output)

        logger.info("Plotting yearly graph...")

        size_x_week: float = self._get_plot_params()["size_x_week"]
        size_y_week: float = self._get_plot_params()["size_y_week"]
        colspan_week_summary = self._get_plot_params()["colspan_week_summary"]
        columns_week = YearlyPlot.columns_days + colspan_week_summary

        size_x_stats: float = self._get_plot_params()["size_x_stats"]
        size_y_stats: float = self._get_plot_params()["size_y_stats"]
        should_print_stats: bool = ("year_stats" in self.parts) and size_y_stats > 0

        fig = plt.figure(figsize=(size_x_week * columns_week, size_y_week * self.rows))

        week_graphs = self._get_plot_params()["week_graphs"]
        week_summary_graphs = self._get_plot_params()["week_summary_graphs"]

        week_ylim = {}
        summary_ylim = {}
        for type in week_graphs.keys():
            ylims = self._compute_week_ylim(type, data)
            factor = self._get_plot_params()["ylim_factor"]
            week_ylim[type] = [
                ylim * factor if ylim != None else None for ylim in ylims
            ]
        for type in week_summary_graphs.keys():
            ylims = self._compute_summary_ylim(type, data)
            factor = self._get_plot_params()["ylim_factor"]
            summary_ylim[type] = [
                ylim * factor * (24 * 7) if ylim != None else None for ylim in ylims
            ]

        align_weekdays = self.output.get("align_weekdays", False)
        if "weeks" in self.parts:
            for index, week in enumerate(self.weeks):
                week_start = datetime.date.fromisocalendar(self.year, week, 1)

                weekly_data = self._get_weekly_data_frame(data, week)
                first: pd.DatetimeIndex = weekly_data.index[0]
                data_start = datetime.date(first.year, first.month, first.day)
                if align_weekdays:
                    shift = (data_start - week_start).days * 24
                    days = 7
                else:
                    shift = 0
                    days = len(weekly_data) // 24
                weekly_index = [x + 0.5 + shift for x in range(len(weekly_data))]

                row = index * self.week_height
                for type, rowspan in week_graphs.items():
                    if type != "spacer":
                        ax = plt.subplot2grid(
                            (self.rows, columns_week),
                            (row, 1),
                            rowspan=rowspan,
                            colspan=7 * YearlyPlot.colspan_day,
                        )
                        ylim_min, ylim_max = week_ylim[type]
                        if ylim_min != ylim_max:
                            ax.set_ylim(ylim_min, ylim_max)
                        self._print_weekly_graph(
                            ax, region, weekly_index, weekly_data, type
                        )
                        self._annotate_weekly_graph(ax, data_start, days, type)
                    row += rowspan

                if "week_summary" in self.parts:
                    row = index * self.week_height
                    for type, rowspan in week_summary_graphs.items():
                        if type != "spacer":
                            ylim_min, ylim_max = summary_ylim[type]
                            ax = plt.subplot2grid(
                                (self.rows, columns_week),
                                (row, columns_week - colspan_week_summary),
                                rowspan=rowspan,
                                colspan=colspan_week_summary,
                            )
                            self._print_summary(
                                ax,
                                region,
                                weekly_data,
                                ylim_min,
                                ylim_max,
                                type,
                                label="",
                                weekly=True,
                            )
                        row += rowspan

        fig.patch.set_facecolor("white")

        if "titles" in self.parts:
            title, subtitle = self._get_titles(region, data)
            subtitle_lines = subtitle.count("\n") + 1
            height = self.rows * self._get_plot_params()["size_y_week"]
            fig.suptitle(
                title,
                size=28,
                y=max(0.89, 1 + 0.012 * subtitle_lines - 0.0023 * height),
            )
            plt.figtext(
                0.5, max(0.884, 0.94 - 0.001 * height), subtitle, size=18, ha="center"
            )

        plt.subplots_adjust(wspace=0, hspace=0)

        weeks_path = (
            self._get_plot_filename(f"{filename_output}-weeks")
            if should_print_stats
            else output_path
        )
        plt.savefig(
            weeks_path, bbox_inches="tight", pad_inches=0.2, dpi=self.output["dpi"]
        )
        plt.close(fig)
        plt.clf()

        if should_print_stats:
            width = size_x_stats * YearlyPlot.columns_stats
            height = size_y_stats * self._get_plot_params()["rows_stats"]
            plt.rcParams["figure.figsize"] = width, height
            fig = plt.figure()
            fig.patch.set_facecolor("white")
            self._plot_additional_graphs(region, data)
            fig.tight_layout()

            stats_path = self._get_plot_filename(f"{filename_output}-stats")
            plt.savefig(
                stats_path, bbox_inches="tight", pad_inches=0.2, dpi=self.output["dpi"]
            )
            plt.close(fig)
            plt.clf()

            if can_arrange(self.output["format"]):
                arrange_plots([weeks_path, stats_path], output_path)
                stats_path.unlink()
                weeks_path.unlink()

        logger.info(f"Plot saved to {output_path}")
        return output_path

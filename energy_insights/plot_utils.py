""" Shared code for output files for plots. """

from os import scandir
from pathlib import Path
from typing import Optional


def get_analysis_out_dir(analysis_name: Optional[str], root_dir="..") -> Path:
    """
    Return the plot output parent dir (and assure it exists).

    Arguments:
        analysis_name: Name of the analysis (if None, the main plot dir is used).

    Returns:
        The output directory for this plot.
    """
    analysis_dir = Path(root_dir, "output")

    if analysis_name is not None:
        analysis_dir /= analysis_name

    if not analysis_dir.exists():
        analysis_dir.mkdir(parents=True)

    return analysis_dir


def get_scenario_out_dir(scenario_name: str, analysis_name: Optional[str], root_dir="..") -> Path:
    """
    Return the scenario output directory (and assure it exists).

    Arguments:
        scenario_name: Name of the scenario (within the analysis).
        analysis_name: Name of the analysis (if None, the main plot dir is used).

    Returns:
        The output directory for this plot.
    """
    analysis_dir = get_analysis_out_dir(analysis_name, root_dir=root_dir)

    out_dir = analysis_dir / scenario_name

    if not out_dir.exists():
        out_dir.mkdir(parents=True)

    return out_dir


def remove_scenario_out_dir_if_empty(out_dir: Path) -> None:
    """
    Removes the scenario output directory, if empty.

    Arguments:
        out_dir: Output dir for the scenario to be removed if empty.
    """
    if not any(scandir(out_dir)):
        out_dir.rmdir()


def get_scenario_out_file(scenario_name: str, run_name: Optional[str], root_dir="..") -> Path:
    """
    Return the scenario png output filename (and assure it's parent dir exists).

    Arguments:
        scenario_name: Name of the scenario (within the analysis).
        analysis_name: Name of the analysis (if None, the main plot dir is used).

    Returns:
        The output png file for this plot.
    """
    analysis_dir = get_analysis_out_dir(run_name, root_dir=root_dir)

    out_file = analysis_dir / f"{scenario_name}.png"

    return out_file

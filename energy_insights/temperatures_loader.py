"""
Loads temperature profiles (based on ČHMÚ daily data).
"""

from pathlib import Path
from typing import Union

import pandas as pd


class TemperaturesLoader:
    temperatures_folder = "temperatures/"

    def __init__(self, data_path: Union[str, Path]):
        self.data_path = Path(data_path)

    def _get_path(self, temperature_profile: str):
        return self.data_path / self.temperatures_folder / temperature_profile

    def load_temperatures(self, temperature_profile, year=None):
        path = self._get_path(temperature_profile)
        df = pd.read_csv(path, index_col="datetime", parse_dates=True)
        if year is None:
            return df
        return df[df.index.year == year]

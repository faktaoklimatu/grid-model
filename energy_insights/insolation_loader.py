"""
Loads insolation profiles (from the https://re.jrc.ec.europa.eu/pvg_tools/en/#HR tool)
"""

import os.path

import pandas as pd

from .hourly_average import HourlyAverage


class InsolationLoader:
    insolation_folder = "solar/"

    def __init__(self, data_path: str):
        self.data_path = data_path

    def _get_path(self, solar_profile: str):
        return os.path.join(self.data_path, self.insolation_folder, solar_profile)

    def load_insolation(self, solar_profile: str, production_key: str, installed_units: float):
        df = pd.read_csv(self._get_path(solar_profile))
        df['time'] = pd.to_datetime(df['time'], format='%Y%m%d:%H%M')
        df.set_index('time', inplace=True)
        insolation = HourlyAverage(df).mean_by_hour()
        # The dataset is in the range [0, 1000], first normalize to [0, 1], then multiply by `installed units`.
        insolation[production_key] = insolation['P'] / 1000 * installed_units
        return insolation.loc[:, production_key]

"""
Takes a Pandas Dataframe and returns average values for each hour (keeping DateTime index)
"""

from typing import Optional

import pandas as pd


class HourlyAverage:
    def __init__(self, df: pd.DataFrame, reindex_to_year: Optional[int] = None):
        self.df = df
        self._reindex_to_year = reindex_to_year

    def mean_by_hour(self):
        # Data from ENTSO-E sometimes contain duplicate rows at the
        # whole hour. Get rid of them by deduplicating first.
        # TODO: Make sure this doesn't break anything as it ignores
        # the index -- what if two rows in distinct hours are otherwise
        # the same?
        df_dedup = self.df.drop_duplicates(keep="first")

        # drop_duplicates() will only return None if `inplace=True`,
        # which is not the case here.
        assert isinstance(df_dedup, pd.DataFrame)

        # Downsample to 1-hour frequency by averaging.
        df_resampled = df_dedup.resample("h").mean()

        if self._reindex_to_year:
            is_requested_leap = pd.Timestamp(self._reindex_to_year, 1, 1).is_leap_year
            is_existing_leap = df_resampled.index[0].is_leap_year

            # Handle the edge cases where one year is leap but
            # the other isn't.
            if is_requested_leap and not is_existing_leap:
                # TODO: Duplicate February 28 as February 29.
                raise NotImplementedError
            elif not is_requested_leap and is_existing_leap:
                is_feb_29 = (df_resampled.index.month == 2) & (df_resampled.index.day == 29)
                df_resampled = df_resampled[not is_feb_29]

            df_resampled.index = (
                df_resampled.index.map(lambda ts: ts.replace(year=self._reindex_to_year))
            )

        return df_resampled

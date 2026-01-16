"""
Provides data structure for country grid for visualization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
from numpy import average

from .grid_plot_utils import Keys
from .logging import get_logger
from .params_utils import sum_merge_dicts
from .region import AggregateRegion, Region
from .sources.basic_source import BasicSourceType, Source
from .sources.flexible_source import FlexibleSource, FlexibleSourceType
from .sources.reserves import ReservesRequirements
from .sources.storage import Storage, StorageType
from .yearly_filter import YearlyFilter

logger = get_logger(__name__)


@dataclass
class CountryGrid:
    country: Region
    data: pd.DataFrame
    basic_sources: dict[BasicSourceType, Source]
    flexible_sources: dict[FlexibleSourceType, FlexibleSource]
    storage: dict[StorageType, Storage]
    num_years: int
    reserves: Optional[ReservesRequirements] = None
    is_complete = False
    """Is this grid the sum of all grids in the model?"""

    def __add__(self, other):
        assert not self.is_complete, "Cannot add the complete grid to another grid"
        assert not other.is_complete, "Cannot add the complete grid to another grid"
        assert (
            self.num_years == other.num_years
        ), "num of years must be same in both grids"

        # The dataframes are summed (as all are absolute values in MW).
        # Ignore missing rows in one of the countries and fill that by zeroes (to avoid NaN).
        data_sum = self.data.add(other.data, fill_value=0)
        # Load before flexibility is special, because it is not always
        # generated. Nonetheless, if one of the grids has it and the
        # other doesn't, the resulting grid's load before flexibility
        # should be consistent -- it is just the gross load if there's
        # no flexibility.
        # TODO: Make sure the same happens for LOAD_BASE, LOAD_EVS and
        # LOAD_HEAT_PUMPS.
        if (
            Keys.LOAD_BEFORE_FLEXIBILITY in self.data.columns
            and Keys.LOAD_BEFORE_FLEXIBILITY not in other.data.columns
        ):
            data_sum[Keys.LOAD_BEFORE_FLEXIBILITY] = (
                self.data[Keys.LOAD_BEFORE_FLEXIBILITY] + other.data[Keys.LOAD]
            )
        elif (
            Keys.LOAD_BEFORE_FLEXIBILITY in other.data.columns
            and Keys.LOAD_BEFORE_FLEXIBILITY not in self.data.columns
        ):
            data_sum[Keys.LOAD_BEFORE_FLEXIBILITY] = (
                other.data[Keys.LOAD_BEFORE_FLEXIBILITY] + self.data[Keys.LOAD]
            )

        # Make an exception for the price column - use weighted average.
        # TODO: Checking existence of PRICE column is a hack to make this work with CountryProblem
        # restricting the data in CountryGrid. Fix.
        # TODO: Do the same for shadow prices?
        if Keys.PRICE in self.data and Keys.PRICE in other.data:
            data_sum[Keys.PRICE] = average(
                [self.data[Keys.PRICE], other.data[Keys.PRICE]],
                axis=0,
                weights=[self.data[Keys.LOAD], other.data[Keys.LOAD]],
            )
        if Keys.PRICE_IMPORT in self.data and Keys.PRICE_IMPORT in other.data:
            try:
                data_sum[Keys.PRICE_EXPORT] = average(
                    [self.data[Keys.PRICE_EXPORT], other.data[Keys.PRICE_EXPORT]],
                    axis=0,
                    weights=[self.data[Keys.EXPORT], other.data[Keys.EXPORT]],
                )
                data_sum[Keys.PRICE_IMPORT] = average(
                    [self.data[Keys.PRICE_IMPORT], other.data[Keys.PRICE_IMPORT]],
                    axis=0,
                    weights=[self.data[Keys.IMPORT], other.data[Keys.IMPORT]],
                )
            except ZeroDivisionError:
                # For aggregates, absolute net imports will add up to
                # zero. In such cases, set import price to zero.
                data_sum[Keys.PRICE_IMPORT] = 0

        if self.reserves and other.reserves:
            reserves = self.reserves + other.reserves
        else:
            reserves = self.reserves or other.reserves

        try:
            return CountryGrid(
                AggregateRegion(self.country + " - " + other.country),
                data_sum,
                sum_merge_dicts(self.basic_sources, other.basic_sources),
                sum_merge_dicts(self.flexible_sources, other.flexible_sources),
                sum_merge_dicts(self.storage, other.storage),
                num_years=self.num_years,
                reserves=reserves,
            )
        except AssertionError as ex:
            logger.exception(f"Bad combination in {self.country} & {other.country}")
            raise ex

    # Implement to allow summing a list of country grids (the sum starts with int 0).
    def __radd__(self, other):
        if other == 0:
            return self
        return self.__add__(other)

    @staticmethod
    def filter_grids(
        grids: dict[Region, CountryGrid], yearly_filter: YearlyFilter
    ) -> dict[Region, CountryGrid]:
        selected_regions: set[Region] = yearly_filter.filter_regions(set(grids.keys()))
        return {
            region: grid for region, grid in grids.items() if region in selected_regions
        }

    @staticmethod
    def aggregate_grids(
        grids: dict[Region, CountryGrid], only_aggregate: bool
    ) -> dict[Region, CountryGrid]:
        if len(grids) <= 1:
            return grids
        output = {}
        # Make sure the aggregate is the first in the dict.
        aggregate_string = ", ".join(grids.keys())
        whole_grid_id = AggregateRegion(aggregate_string)
        output[whole_grid_id] = sum(grid for grid in grids.values())
        output[whole_grid_id].is_complete = True
        if only_aggregate:
            return output
        return output | grids

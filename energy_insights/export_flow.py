"""
Provides DAG walking that respects export flows (so that exporting countries are visited before
importers).
"""

import pandas as pd
import numpy as np

from .params_library.interconnectors import (
    Interconnectors,
    Interconnector,
    OUTFLOW_CAPACITY_COST_EUR_PER_MWH
)
from .region import Region
from .country_grid import CountryGrid
from .grid_plot_utils import (
    Keys,
    get_export_key,
    get_import_key,
    get_small_threshold,
)


class ExportFlow:
    def __init__(
        self,
        interconnectors: Interconnectors,
        grids: dict[Region, CountryGrid],
        include_transmission_loss_in_price: bool
    ) -> None:
        self.interconnectors = interconnectors
        self.grids = grids
        self.include_transmission_loss_in_price = include_transmission_loss_in_price

    def _get_countries_without_import(self, index: np.datetime64) -> list[Region]:
        countries: list[Region] = []
        for country in self.grids.keys():
            slice = self._get_slice(country, index)
            if slice[Keys.IMPORT] < get_small_threshold():
                countries.append(country)
        return countries

    def _get_slice(self, country: Region, index: np.datetime64) -> pd.Series:
        return self.grids[country].data.loc[index]

    def _get_real_importers_from(self, from_country: Region, slice: pd.Series) -> set[Region]:
        """
        Calculate the set of neighbours importing from the given region.
        """
        importers: set[Region] = set()
        targets = self.interconnectors.get_connections_from(from_country)
        for country_to, interconnector in targets.items():
            export_key = get_export_key(country_to)
            if interconnector.capacity_mw > 0 and slice[export_key] > 0:
                importers.add(country_to)
        return importers

    def _get_real_exporters_to(self, to_country: Region, slice: pd.Series) -> set[Region]:
        """
        Calculate the set of neighbours exporting to the given region.
        """
        exporters: set[Region] = set()
        sources = self.interconnectors.get_connections_to(to_country)
        for country_from, interconnector in sources.items():
            import_key = get_import_key(country_from)
            if interconnector.capacity_mw > 0 and slice[import_key] > 1e-3:
                exporters.add(country_from)
        return exporters

    def get_order(self, index: np.datetime64) -> list[Region]:
        processed: set[Region] = set()
        order: list[Region] = []
        candidates: list[Region] = self._get_countries_without_import(index)
        to_be_processed: list[Region] = []

        def should_become_candidate(country_to: Region, interconnector: Interconnector) -> bool:
            if interconnector.capacity_mw == 0:
                return False
            if country_to in processed:
                return False
            if country_to in candidates:
                return False
            return True

        while candidates:
            for country in candidates:
                slice = self._get_slice(country, index)
                exporters: set[Region] = self._get_real_exporters_to(country, slice)
                if exporters <= processed:
                    to_be_processed.append(country)

            assert len(to_be_processed) > 0, "in each iteration some country must be processed."
            for country in to_be_processed:
                processed.add(country)
                order.append(country)
                candidates.remove(country)
                if country in self.interconnectors.from_to:
                    for country_to, interconnector in self.interconnectors.from_to[country].items():
                        if should_become_candidate(country_to, interconnector):
                            candidates.append(country_to)
            to_be_processed.clear()

        return order

    def get_export_price(self, country: Region, index: np.datetime64) -> float:
        """
        Calculate the export price of a given region as the maxium of
        import prices in importing neighbours.
        """
        slice = self._get_slice(country, index)

        importers = self._get_real_importers_from(country, slice)
        export_price = 0
        # Export price in my country is the maximum import price over
        # my importing neighbours.
        for importer in importers:
            importer_slice = self._get_slice(importer, index)
            export_price = max(export_price, importer_slice[Keys.PRICE_IMPORT])
        return export_price

    def get_import_price(self, country: Region, index: np.datetime64) -> float:
        """
        Calculate the import price in a given region as the maximum of
        spot prices in exporting neighbours.
        """
        slice = self._get_slice(country, index)

        neighbours = self._get_real_exporters_to(country, slice)
        import_price = 0
        # Import price in my country is the maximum price over my
        # exporting neighbours.
        for neighbour in neighbours:
            neighbour_slice = self._get_slice(neighbour, index)
            neighbour_price = neighbour_slice[Keys.PRICE]

            if self.include_transmission_loss_in_price:
                # Increase the price proportionally to the transmission loss. This does not correspond
                # to the current model but the future market will need to value electricity transit.
                loss = self.interconnectors.from_to[neighbour][country].loss
                import_price = max(import_price, neighbour_price / (1 - loss))
            else:
                import_price = max(import_price, neighbour_price)

        # Increase the price by the small interconnector fee (that is included in optimization).
        return import_price + OUTFLOW_CAPACITY_COST_EUR_PER_MWH

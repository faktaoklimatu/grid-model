"""
Structures for sources of heat in the grid for heat supply modelling.
"""

from dataclasses import dataclass


@dataclass
class HeatSource:
    pass


@dataclass
class BackPressureTurbine(HeatSource):
    ratio_heat_mw_per_el_mw: float
    """How many MW of heat get produced per MW of electricity. The heat
    production is unavoidable for this turbine and thus cannot get
    easily curtailed."""

    @staticmethod
    def canonical() -> "BackPressureTurbine":
        """Return a canonical instance of the turbine with some
        sensible default parameters.
        """
        return BackPressureTurbine(ratio_heat_mw_per_el_mw=3)


@dataclass
class ExtractionTurbine(HeatSource):
    base_ratio_heat_mw_per_el_mw: float
    """How many MW of heat get produced per MW of electricity when no
    steam gets extracted (which is the maximum-electricity setting)."""
    heat_mw_per_decreased_el_mw: float
    """How many MW of heat can get "traded" per 1 MW of electricity
    (by extracting steam)."""
    min_ratio_el: float
    """Minimum allowed proportion of electricity production (when steam
    extraction is at its maximum), in terms of MW_e."""

    @staticmethod
    def canonical() -> "ExtractionTurbine":
        """Return a canonical instance of the turbine with some
        sensible default parameters.
        """
        return ExtractionTurbine(
            base_ratio_heat_mw_per_el_mw=0,
            heat_mw_per_decreased_el_mw=3,
            min_ratio_el=0.4,
        )


@dataclass
class HeatRecoveryUnit(HeatSource):
    max_heat_mw_per_el_mw: float
    """How much heat may be at most generated per unit of electricity
    produced by recovering exhaust heat."""

    @staticmethod
    def canonical() -> "HeatRecoveryUnit":
        """Return a canonical instance of the heat recovery unit with
        some sensible default parameters.
        """
        return HeatRecoveryUnit(max_heat_mw_per_el_mw=1)

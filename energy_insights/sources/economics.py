"""
Unified structure for maintaining the costs and other parameters
related to the financing, construction and operations of a power
source.
"""

# TODO: Unify or extend with InputCosts?

from dataclasses import dataclass
from typing import Optional


@dataclass
class SourceEconomics:
    """Economic parameters related to the funding, construction and
    operations of a power source.
    """

    overnight_costs_per_kw_eur: float
    decommissioning_cost_per_kw_eur: float
    construction_time_years: int
    """Assuming costs are spread linearly over the years."""
    lifetime_years: int
    """Fixed lifetime, independent of usage."""
    # Lifetime may be also specified in hours of full utilization. In this case, this number is
    # what mainly determines the costs, lifetime_years is only used as a supportive figure to
    # estimate interest costs (in the linear optimization).
    lifetime_hours: Optional[int]
    decommissioning_time_years: int
    """Assuming costs are spread linearly over the years."""
    fixed_o_m_costs_per_kw_eur: float
    """Part of operations and maintenance (O&M) that is independent of
    the capacity factor."""
    variable_costs_per_mwh_eur: float
    """Includes fuel, carbon price, and variable part of O&M."""
    discount_rate: float
    """Discount rate as a multiplicative factor, e.g. 1.05 denotes
    a 5% rate."""


def extract_economics_params(source: dict) -> dict:
    economics_dict = {
        # Set non-trivial default values.
        "decommissioning_time_years": source.pop("decommissioning_time_years", 2),
        "discount_rate": source.pop("discount_rate", 1.08),
        "overnight_costs_per_kw_eur": source.pop("overnight_costs_per_kw_eur", 0),
        # Set trivial default values.
        "fixed_o_m_costs_per_kw_eur": source.pop("fixed_o_m_costs_per_kw_eur", 0),
        "lifetime_hours": source.pop("lifetime_hours", None),
        "variable_costs_per_mwh_eur": source.pop("variable_costs_per_mwh_eur", 0),
        # Set non-zero to avoid division by zero.
        "construction_time_years": source.pop("construction_time_years", 1),
        "lifetime_years": source.pop("lifetime_years", 1),
    }

    # Compute decommissioning costs based on a given ratio of overnight costs.
    decommissioning_cost_ratio = source.pop("decommissioning_cost_ratio", 0.05)
    economics_dict["decommissioning_cost_per_kw_eur"] = (
        economics_dict["overnight_costs_per_kw_eur"] *
        decommissioning_cost_ratio
    )

    return economics_dict


def usd_to_eur_2022(usd: float) -> float:
    return usd * 0.95

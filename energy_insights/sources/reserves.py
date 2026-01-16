"""
Specifies required amounts of capacity reserves.
"""

import math

from dataclasses import dataclass


@dataclass
class ReservesRequirements:
    fcr: float
    frr: float

    def __add__(self, other):
        assert isinstance(
            other, ReservesRequirements
        ), "Cannot add a non-ReservesRequirements object to ReservesRequirements"

        fcr_total = self.fcr + other.fcr
        frr_total = self.frr + other.frr

        return ReservesRequirements(fcr=fcr_total, frr=frr_total)

    def __post_init__(self):
        if not math.isfinite(self.fcr) or self.fcr < 0:
            raise ValueError("FCR requirement must be nonnegative")
        if not math.isfinite(self.frr) or self.frr < 0:
            raise ValueError("FRR requirement must be nonnegative")


@dataclass
class BaseReservesProvider:
    max_installed_fraction: float = 1.0
    """Maximum fraction of installed capacity that can be used as
    a reserve capacity."""
    min_dispatch_fraction: float = 0.0
    """Minimum required dispatch relative to committed capacity. Note
    that this has no effect in the case of storage (including hydro)
    which has implicit 100% commitment in both direction and no minimum
    dispatch requirements."""

    def __post_init__(self) -> None:
        if not (0.0 <= self.max_installed_fraction <= 1.0):
            raise ValueError(
                f"Maximum commitment fraction (currently {self.max_installed_fraction}) must be"
                " between 0 and 1"
            )
        if not (0.0 <= self.min_dispatch_fraction <= 1.0):
            raise ValueError(
                f"Minimum dispatch fraction (currently {self.min_dispatch_fraction}) must be"
                " between 0 and 1"
            )


@dataclass
class FastReservesProvider(BaseReservesProvider):
    pass


@dataclass
class SlowReservesProvider(BaseReservesProvider):
    pass

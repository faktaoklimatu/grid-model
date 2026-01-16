"""
Provides parameters for basic sources in the grid.
"""

import enum
from copy import deepcopy
from dataclasses import dataclass, field, fields
from typing import NamedTuple, Optional, Union


from .reserves import BaseReservesProvider
from ..color_map import ColorMap
from ..grid_opex_utils import get_ramp_up_cost_per_mw_eur
from ..logging import get_logger
from ..region import Zone
from ..sources.economics import SourceEconomics, extract_economics_params

logger = get_logger(__name__)


@enum.unique
class BasicSourceType(enum.StrEnum):
    """
    Provides an enum for basic sources taken from entsoe data.
    """

    HYDRO = "hydro"
    NUCLEAR = "nuclear"
    OFFSHORE = "offshore"
    ONSHORE = "onshore"
    SOLAR = "solar"
    WIND = "wind"  # Aggregate of onshore and offshore.

    def get_factor_key(self) -> str:
        if self == BasicSourceType.WIND:
            raise ValueError("Aggregate wind type not supported")
        return f"generation_{self.value}"

    def is_variable_renewable(self) -> bool:
        return self.is_wind() or self == BasicSourceType.SOLAR

    def is_wind(self) -> bool:
        return (
            self == BasicSourceType.ONSHORE
            or self == BasicSourceType.OFFSHORE
            or self == BasicSourceType.WIND
        )


class ProfileOverride(NamedTuple):
    """Triple specifying the ENTSO-E country, installed capacity in GW
    and source type for production profile override."""

    country: Zone
    installed_gw: float
    source_type: Optional[BasicSourceType] = None


@dataclass
class Source:
    # Unique identifier of this source.
    type: BasicSourceType
    # Color for this source, only used for plots.
    color: str
    # The default installed capacity of the source (that can be decreased by capacity optimization).
    capacity_mw: float
    # The minimal installed capacity of this source, used in capacity optimization.
    min_capacity_mw: float
    # Capacity of the source that is considered already paid off. Must be lower or equal to the
    # minimal installed capacity of this source. This means that paid off capacity does not
    # influence optimization, it only decreases total system costs (for this source and overall).
    # This param however does not influence average system costs per MWh for this source (production
    # using the paid off capacity is not counted for the average). The reason is not to skew the
    # figure so that economics of the remaining capacity (not paid off) can be evaluated.
    paid_off_capacity_mw: float
    # Is this source classified as renewable by the EU? (only used for statistics)
    renewable: bool
    # Is this source virtual (such as "loss-of-load" source that helps meet the optimization
    # constraints) -- only used for statistics (virtual sources are not plotted).
    virtual: bool
    # Carbon intensity of this source - used for statistics and for computing variable costs.
    co2_t_mwh: float
    # Various fixed and variable costs and parameters for capex optimization.
    economics: SourceEconomics
    # Override the production curve using data from the given country
    # and source type instead of the default.
    profile_override: Optional[ProfileOverride] = field(default=None, kw_only=True)
    reserves: Optional[BaseReservesProvider] = field(default=None, kw_only=True)

    def __add__(self, other):
        assert self.type == other.type
        assert self.color == other.color
        assert self.virtual == other.virtual

        # TODO: Consider reverting this to an assert after nuclear study is completed.
        # NOTE: Uses the dataclass implicit __eq__ method.
        if self.economics != other.economics:
            logger.warning(
                f"Different economics for {self.type}, picking (randomly) one of the values, "
                "summary graphs will be wrong"
            )

        if self.reserves != other.reserves:
            raise ValueError("Summed sources must provide the same kind of reserves")

        return Source(
            type=self.type,
            color=self.color,
            capacity_mw=self.capacity_mw + other.capacity_mw,
            min_capacity_mw=self.min_capacity_mw + other.min_capacity_mw,
            paid_off_capacity_mw=self.paid_off_capacity_mw + other.paid_off_capacity_mw,
            renewable=self.renewable,
            virtual=self.virtual,
            co2_t_mwh=self.co2_t_mwh,
            economics=deepcopy(self.economics),
            profile_override=None,
            reserves=deepcopy(self.reserves),
        )


@dataclass
class FlexibleBasicSource(Source):
    """FlexibleBasicSource supports two modes of decreasing production
    each of them imposing a constraint. These two modes
    (`max_decrease_mw` and `min_production_mw`) can be combined.
    """

    max_decrease_mw: float
    """Maximum decrease of production compared to the fixed production
    curve.

    This value is decreased by the current output ratio (if the fixed
    production curve of the source is currently at 100% of its nominal
    output, production can be decreased by up to `max_decrease_mw`; if
    the source currently operates at 50% of its nominal output,
    production can be decreased by `max_decrease_mw`/2). This
    approximately models that the source is composed of multiple units
    so the ability to decrease production shrinks as the number of
    operating units shrinks."""

    min_production_mw: float
    """Minimum level to which production can sink (unless the fixed
    production curve is below this level). This allows flexibility
    between the fixed curve and this minimum level. In hours with the
    fixed production curve below `min_production_mw`, production
    follows the fixed curve with no flexibility."""

    ramp_rate: float
    """Power (expressed as ratio of `capacity_mw`) by which the current
    production can change up or down in one hour (within the
    flexibility described above)."""

    ramp_up_cost_mw_eur: float
    """Fixed cost for increasing output by 1 MW."""

    def is_truly_flexible(self):
        return self.max_decrease_mw > 0 and self.min_production_mw < self.capacity_mw

    def __add__(self, other):
        basic_source = Source.__add__(self, other)
        source_dict = {
            field.name: getattr(basic_source, field.name) for field in fields(Source)
        }

        assert self.ramp_rate == other.ramp_rate
        assert self.ramp_up_cost_mw_eur == other.ramp_up_cost_mw_eur

        return FlexibleBasicSource(
            **source_dict,
            max_decrease_mw=self.max_decrease_mw + other.max_decrease_mw,
            min_production_mw=self.min_production_mw + other.min_production_mw,
            ramp_rate=self.ramp_rate,
            ramp_up_cost_mw_eur=self.ramp_up_cost_mw_eur,
        )


@dataclass
class ProfiledBasicSource(Source):
    profile_name: str

    def __add__(self, other):
        basic_source = Source.__add__(self, other)
        source_dict = {
            field.name: getattr(basic_source, field.name) for field in fields(Source)
        }
        assert self.profile_name == other.profile_name
        return ProfiledBasicSource(
            **source_dict,
            profile_name=self.profile_name,
        )


# 9.33 USD_2018 according to IEA Projected Costs of Generating Electricity 2020:
# https://iea.blob.core.windows.net/assets/ae17da3d-e8a5-4163-a3ec-2e6fb0b5677d/Projected-Costs-of-Generating-Electricity-2020.pdf
NUCLEAR_FUEL_PRICE_EUR_MWH_EL = 10.51
__nuclear_efficiency = 0.33
__nuclear_fuel_price_eur_mwh_LHV = NUCLEAR_FUEL_PRICE_EUR_MWH_EL * __nuclear_efficiency
__flexible_nuclear_ramp_rate = 0.5

# Based on PEMMDB.
__flexible_nuclear_ramp_up_cost_mw_eur = get_ramp_up_cost_per_mw_eur(
    wear_cost_per_mw_eur=21,
    ramp_fuel_per_mw_gj=8,  # Assuming lower consumption for hot nuclear (PEMMDB does not specify).
    fuel_cost_per_mwh_LWH=__nuclear_fuel_price_eur_mwh_LHV,
)


__renewable = {
    "construction_time_years": 1,
    "lifetime_years": 25,
    "variable_costs_per_mwh_eur": 0,
    "renewable": True,
}

__solar = __renewable | {
    "type": BasicSourceType.SOLAR,
    "color": ColorMap.SOLAR,
    # IEA World Energy Outlook 2024, Stated Policies Scenario, page 333,
    # average of EU costs in 2023 and 2030.
    # https://iea.blob.core.windows.net/assets/140a0470-5b90-4922-a0e9-838b3ac6918c/WorldEnergyOutlook2024.pdf#page=333
    "overnight_costs_per_kw_eur": 568,
    # Based on O&M/MWh and assumed capacity factors.
    "fixed_o_m_costs_per_kw_eur": 11,
    # Assuming closer to the optimistic end of the range in the IEA
    # study (as Europe is  stable market).
    "discount_rate": 1.05,
}

__onshore = __renewable | {
    "type": BasicSourceType.ONSHORE,
    "color": ColorMap.WIND,
    # IEA World Energy Outlook 2024, Stated Policies Scenario, page 333,
    # average of EU costs in 2023 and 2030.
    # https://iea.blob.core.windows.net/assets/140a0470-5b90-4922-a0e9-838b3ac6918c/WorldEnergyOutlook2024.pdf#page=333
    "overnight_costs_per_kw_eur": 1469,
    "fixed_o_m_costs_per_kw_eur": 32,
    # Assuming closer to the optimistic end of the range in the IEA study (as Europe is stable market).
    "discount_rate": 1.05,
}

__offshore = __renewable | {
    "type": BasicSourceType.OFFSHORE,
    "color": ColorMap.WIND,
    # IEA World Energy Outlook 2024, Stated Policies Scenario, page 333,
    # average of EU costs in 2023 and 2030.
    # https://iea.blob.core.windows.net/assets/140a0470-5b90-4922-a0e9-838b3ac6918c/WorldEnergyOutlook2024.pdf#page=333
    "overnight_costs_per_kw_eur": 2568,
    "fixed_o_m_costs_per_kw_eur": 62,
    # Assuming closer to the optimistic end of the range in the IEA study
    # (as Europe is a stable market).
    "discount_rate": 1.06,
}

__hydro_reservoir = {
    "type": BasicSourceType.HYDRO,
    "color": ColorMap.HYDRO,
    "construction_time_years": 5,
    "lifetime_years": 80,
    "variable_costs_per_mwh_eur": 4,
    # Based on Ember's New Generation report (for 2020), average between RoR and reservoir hydro.
    "overnight_costs_per_kw_eur": 2700,
    "fixed_o_m_costs_per_kw_eur": 15,
    "renewable": True,
}

__conventional_nuclear_new_build = {
    "type": BasicSourceType.NUCLEAR,
    "color": ColorMap.NUCLEAR,
    "construction_time_years": 7,
    "lifetime_years": 60,
    "decommissioning_time_years": 10,
    "decommissioning_cost_ratio": 0.15,
    "variable_costs_per_mwh_eur": NUCLEAR_FUEL_PRICE_EUR_MWH_EL + 10,
    # IEA World Energy Outlook 2024, Stated Policies Scenario, page 333,
    # average of EU costs in 2023 and 2030.
    # https://iea.blob.core.windows.net/assets/140a0470-5b90-4922-a0e9-838b3ac6918c/WorldEnergyOutlook2024.pdf#page=333
    "overnight_costs_per_kw_eur": 5560,
    "fixed_o_m_costs_per_kw_eur": 95,
    "renewable": False,
    # Make it flexible by default with zero flexibility.
    "flexible": True,
    "max_decrease_mw": 0,
    "ramp_rate": __flexible_nuclear_ramp_rate,
    "ramp_up_cost_mw_eur": __flexible_nuclear_ramp_up_cost_mw_eur,
}

basic_source_defaults: dict[BasicSourceType, dict] = {
    BasicSourceType.HYDRO: __hydro_reservoir,
    BasicSourceType.NUCLEAR: __conventional_nuclear_new_build,
    BasicSourceType.OFFSHORE: __offshore,
    BasicSourceType.ONSHORE: __onshore,
    BasicSourceType.SOLAR: __solar,
}

_basic_sources: dict[str, dict[BasicSourceType, dict]] = {}


def fix_source_params(source: dict) -> dict:
    # Set non-trivial default values.
    source.setdefault("capacity_mw", 0.0)
    source.setdefault("min_capacity_mw", 0.0)
    source.setdefault("paid_off_capacity_mw", 0.0)
    source.setdefault("renewable", False)
    source.setdefault("virtual", False)
    source.setdefault("co2_t_mwh", 0.0)
    # TODO: Workaround for Python < 3.10. See the field declaration above.
    source.setdefault("profile_override", None)

    # Paid off capacity can't be above min capacity (it is not accounted for in optimization).
    assert (
        source["paid_off_capacity_mw"] <= source["min_capacity_mw"]
    ), f"{source['type']} paid off capacity must be below min capacity for optimization"
    return source


def _fix_flexible_basic_source_params(source: dict) -> dict:
    source = fix_source_params(source)
    source.setdefault("max_decrease_mw", source["capacity_mw"])
    source.setdefault("min_production_mw", 0.0)
    source.setdefault("ramp_rate", 1.0)
    source.setdefault("ramp_up_cost_mw_eur", 0.0)
    return source


def fix_profiled_basic_source_params(source: dict) -> dict:
    source = fix_source_params(source)
    return source


def get_basic_sources(
    sources: Union[str, dict[BasicSourceType, dict]],
) -> dict[BasicSourceType, Source]:
    def create_source(key: BasicSourceType, params_add: dict) -> Source:
        params = basic_source_defaults[key] | params_add
        economics = SourceEconomics(**extract_economics_params(params))

        if params.pop("flexible", False):
            source_dict = _fix_flexible_basic_source_params(params)
            return FlexibleBasicSource(
                economics=economics,
                **source_dict,
            )

        source_dict = fix_source_params(params)
        return Source(economics=economics, **source_dict)

    if isinstance(sources, str):
        sources_dict = deepcopy(_basic_sources[sources])
    else:
        sources_dict = deepcopy(sources)

    return {key: create_source(key, item) for key, item in sources_dict.items()}

"""
Code for validating that historical dispatch data, as fetched from ENTSO-E is sound.

This code is a slightly modified version of
https://github.com/electricitymaps/electricitymaps-contrib/blob/ac2a3c41a41f779b79fe61d5a2e489bdb2d0cb3d/parsers/lib/validation.py
licensed under GNU-AGPLv3.
"""

import math
from typing import Any, Tuple, Union

from .logging import get_logger
from .region import Zone

logger = get_logger(__name__)


def _has_value_for_key(zone_key: Zone, datapoint: dict[str, Any], key: str) -> bool:
    """
    Checks that the key exists in datapoint and that the corresponding value is not None.
    """
    value = datapoint["production"].get(key, None)
    if value is None or math.isnan(value):
        # TODO: Use a logger once we have a proper logging solution in place.
        logger.warning(f"Required generation type {key} is missing from {zone_key}")
        return False
    return True


def _check_expected_range(
    zone_key: Zone,
    value: Union[float, int],
    expected_range: Tuple[float, float],
    key: Union[str, None] = None,
) -> bool:
    """
    Checks that the `value` is within the `expected_range`. `zone_key` and `key` are only used for logging.
    """
    low, high = min(expected_range), max(expected_range)
    if not (low <= value <= high):
        key_str = "for key `{}`".format(key) if key else ""
        # TODO: Use a logger once we have a proper logging solution in place.
        logger.warning(
            f"{zone_key} reported total of {value:.2f} MW falls outside range "
            f"of {expected_range} {key_str}"
        )
        return False
    return True


def validate_entsoe(
    zone_key: Zone,
    datapoint: dict,
    **kwargs,
) -> Union[dict[str, Any], None]:
    """
    Validates a production datapoint based on given constraints.
    If the datapoint is found to be invalid then None is returned.

    Arguments:
        zone_key: zone key of the datapoint
        datapoint: a production datapoint. See examples
    optional keyword arguments
        remove_negative: bool
            Changes negative production values to None.
            Defaults to False.
        required: list
            Generation types that must be present.
            For example ['gas', 'hydro']
            If any of these types are None the datapoint will be invalidated.
            Defaults to an empty list.
        floor: float | int
            Checks production sum is above floor value.
            If this is not the case the datapoint is invalidated.
            Defaults to None
        expected_range: tuple | dict
            Checks production total against expected range.
            Tuple is in form (low threshold, high threshold), e.g. (1800, 12000).
            If a dict, it should be in the form
            {
            'nuclear': (low, high),
            'coal': (low, high),
            }
        fake_zeros: bool
            Check if there are fake zeros, eg all values are 0 or None
        All keys will be required.
        If the total is outside this range the datapoint will be invalidated.
        Defaults to None.

    Returns: The provided `datapoint` (potentially slightly modified, see keyword arguments above) if the datapoint is valid, None otherwise.

    Examples:
    >>> test_datapoint = {
    >>>   'datetime': '2017-01-01T00:00:00Z',
    >>>       'production': {
    >>>           'Biomass': 50.0,
    >>>           'Coal': 478.0,
    >>>           'Gas': 902.7,
    >>>           'Hydro': 190.1,
    >>>           'Nuclear': None,
    >>>           'Oil': 0.0,
    >>>           'Solar': 20.0,
    >>>           'Wind': 40.0,
    >>>           'Geothermal': 0.0,
    >>>           'Unknown': 6.0
    >>>       },
    >>>       'storage': {
    >>>           'hydro': -10.0,
    >>>       },
    >>>       'source': 'mysource.com'
    >>> }
    >>> validate(datapoint, None, required=['gas'], expected_range=(100, 2000))
    datapoint
    >>> validate(datapoint, None, required=['not_a_production_type'])
    None
    >>> validate(datapoint, None, required=['gas'],
    >>>          expected_range={'solar': (0, 1000), 'wind': (100, 2000)})
    datapoint
    """
    remove_negative: bool = kwargs.pop("remove_negative", False)
    required: list[Any] = kwargs.pop("required", [])
    floor: Union[float, int, None] = kwargs.pop("floor", None)
    expected_range: Union[Tuple, dict, None] = kwargs.pop("expected_range", None)
    fake_zeros: bool = kwargs.pop("fake_zeros", False)

    if kwargs:
        raise TypeError("Unexpected **kwargs: %r" % kwargs)

    production: dict[str, Any] = datapoint["production"]
    storage: dict[str, Any] = datapoint.get("storage", {})

    if remove_negative:
        for key, val in production.items():
            if val is not None and -5.0 < val < 0.0:
                # TODO: Use a logger once we have a proper logging solution in place.
                logger.warning(
                    f"{key} returned {val:.2f} for zone {zone_key}, setting to None"
                )
                production[key] = None

    if required:
        for item in required:
            if not _has_value_for_key(zone_key, datapoint, item):
                return

    if floor:
        # when adding power to the system, storage key is negative
        total = sum(v for k, v in production.items() if v is not None) - sum(
            v for k, v in storage.items() if v is not None
        )
        if total < floor:
            # TODO: Use a logger once we have a proper logging solution in place.
            logger.warning(
                f"{zone_key} reported total of {total} MW does not meet {floor} MW floor value"
            )
            return

    if expected_range:
        if isinstance(expected_range, dict):
            for key, range_ in expected_range.items():
                if not _has_value_for_key(zone_key, datapoint, key):
                    return
                if not _check_expected_range(
                    zone_key, production[key], range_, key=key
                ):
                    return
        else:
            # when adding power to the system, storage key is negative
            total = sum(v for k, v in production.items() if v is not None) - sum(
                v for k, v in storage.items() if v is not None
            )
            if not _check_expected_range(zone_key, total, expected_range):
                return

    if fake_zeros:
        if all((val == 0) or (val is None) for val in production.values()):
            # TODO: Use a logger once we have a proper logging solution in place.
            logger.warning(
                f"{zone_key} - {datapoint['datetime']}: unrealistic datapoint,"
                "all production values are 0.0 MW or null"
            )
            return

    return datapoint

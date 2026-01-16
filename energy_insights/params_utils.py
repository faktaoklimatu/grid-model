""" Shared code for deep merging dicts of params. """

from copy import deepcopy
from typing import Optional

from .region import AggregateRegion, Region, Zone


def _sum_lists_of_dicts_by_type(a: list, b: list):
    map_a = {x["type"]: x for x in a}
    map_b = {x["type"]: x for x in b}
    common_keys = map_a.keys() & map_b.keys()
    common_values = [map_a[key] | map_b[key] for key in common_keys]
    a_values = [map_a[key] for key in map_a.keys() - common_keys]
    b_values = [map_b[key] for key in map_b.keys() - common_keys]
    return common_values + a_values + b_values


def _merge_config_into_scenario(config: dict, scenario: dict, path_for_debugging: list[str]) -> dict:
    for key in config:
        if key in scenario:
            path_str = '.'.join(path_for_debugging + [str(key)])
            if isinstance(config[key], dict) and isinstance(scenario[key], dict):
                new_path_for_debugging = path_for_debugging + [str(key)]
                _merge_config_into_scenario(config[key], scenario[key], new_path_for_debugging)
            elif isinstance(config[key], list) and isinstance(scenario[key], list):
                # Make one exception for storage lists.
                # TODO: remove once storage is changed into dicts
                if key == "storage":
                    # Pass scenario as the second param so that its value wins.
                    scenario[key] = _sum_lists_of_dicts_by_type(config[key], scenario[key])
                else:
                    assert config[key] == scenario[
                        key], f"merging of lists is not supported at {path_str}"
            else:
                assert type(config[key]) == type(
                    scenario[key]), f"merging of different types is not supported at {path_str}"
                # If the values are different, keep the value of scenario, no need to do anything.
        else:
            scenario[key] = config[key]
    return scenario


def merge_config_into_scenario(config: dict, scenario: dict) -> dict:
    """
    Merges the deep config dict into (a copy of the) the deep scenario dict and returns the result.
    For conflicts, scenario wins over config. Type structure for overlapping keys must match. Lists
    values must be equal, no merging for lists is supported.
    """
    return _merge_config_into_scenario(config, deepcopy(scenario), [])


def sum_lists_by_type(a: list, b: list):
    map_a = {x.type: x for x in a}
    map_b = {x.type: x for x in b}
    common_keys = map_a.keys() & map_b.keys()
    common_values = [map_a[key] + map_b[key] for key in common_keys]
    a_values = [map_a[key] for key in map_a.keys() - common_keys]
    b_values = [map_b[key] for key in map_b.keys() - common_keys]
    return common_values + a_values + b_values


def get_country_aggregate(country_params: dict) -> Optional[AggregateRegion]:
    if "in_aggregate" in country_params:
        return country_params["in_aggregate"]
    return None


def get_country_or_aggregate(country: Zone, country_params: dict) -> Region:
    aggregate = get_country_aggregate(country_params)
    return country if aggregate is None else aggregate


def sum_merge_dicts(left: dict, right: dict) -> dict:
    """
    Merge dictionaries by summing values with the same key and
    including values with unique keys from both dicts.
    """
    keys_left = left.keys()
    keys_right = right.keys()

    # First sum the common keys.
    merged = {
        key: left[key] + right[key]
        for key in keys_left & keys_right
    }

    # Add unique keys from the left.
    merged.update({
        key: value for key, value in left.items()
        if key not in keys_right
    })

    # Add unique keys from the right.
    merged.update({
        key: value for key, value in right.items()
        if key not in keys_left
    })

    return merged

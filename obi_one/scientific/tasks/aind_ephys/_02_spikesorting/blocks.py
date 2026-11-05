"""What the sorters' parameter blocks share."""

import copy

from obi_one.core.block import Block


def deep_merge(defaults: dict, overrides: dict) -> dict:
    """``defaults`` with ``overrides`` applied, merging nested dicts key by key."""
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class SorterParameters(Block):
    """A theme of a sorter's parameters.

    ``to_dict`` gives what overrides spikeinterface's defaults for the sorter. By default that is
    the block's fields, whose names are then the sorter's own.
    """

    def to_dict(self) -> dict:
        return self.model_dump(exclude={"type"})

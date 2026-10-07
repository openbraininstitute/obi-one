"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.blocks.synaptic_models.domains import (
    ceil,
    clip_parameter_samples,
    floor,
    highest_allowed,
    inf,
    is_valid_parameter_sample,
    isfinite,
    isinf,
    isnan,
    L,
    logging,
    lowest_allowed,
    NamedTuple,
    nextafter,
    ParameterDomain,
)

from obi_one_lazy.scientific.blocks.synaptic_models.domains import (
    _EXAMPLES_IN_MESSAGE,
)

__all__ = [
    "ceil",
    "clip_parameter_samples",
    "floor",
    "highest_allowed",
    "inf",
    "is_valid_parameter_sample",
    "isfinite",
    "isinf",
    "isnan",
    "L",
    "logging",
    "lowest_allowed",
    "NamedTuple",
    "nextafter",
    "ParameterDomain",
    "_EXAMPLES_IN_MESSAGE",
]

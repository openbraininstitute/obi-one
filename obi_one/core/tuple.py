"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.tuple import (
    Any,
    NamedTuple,
    NamedTupleBase,
    NonNegativeInt,
    OBIBaseModel,
)

__all__ = [
    "Any",
    "NamedTuple",
    "NamedTupleBase",
    "NonNegativeInt",
    "OBIBaseModel",
]

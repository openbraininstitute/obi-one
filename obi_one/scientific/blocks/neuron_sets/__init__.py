"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.neuron_sets import (
    base,
    combined,
    constants,
    deprecated,
    id,
    population,
    predefined,
    property,
    specific,
)

__all__ = [
    "base",
    "combined",
    "constants",
    "deprecated",
    "id",
    "population",
    "predefined",
    "property",
    "specific",
]

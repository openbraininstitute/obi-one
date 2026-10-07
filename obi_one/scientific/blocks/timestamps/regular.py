"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.timestamps.regular import (
    ClassVar,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    RegularTimestamps,
    SchemaKey,
    Timestamps,
    UIElement,
    Units,
)

__all__ = [
    "ClassVar",
    "Field",
    "NonNegativeFloat",
    "NonNegativeInt",
    "RegularTimestamps",
    "SchemaKey",
    "Timestamps",
    "UIElement",
    "Units",
]

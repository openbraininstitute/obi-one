"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.timestamps.single import (
    ClassVar,
    SingleTimestamp,
    Timestamps,
)

__all__ = [
    "ClassVar",
    "SingleTimestamp",
    "Timestamps",
]

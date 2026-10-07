"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.timestamps import (
    base,
    regular,
    single,
)

__all__ = [
    "base",
    "regular",
    "single",
]

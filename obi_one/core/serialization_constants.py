"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.serialization_constants import (
    COORDINATE_CONFIG_FILENAME,
    SCAN_CONFIG_FILENAME,
)

__all__ = [
    "COORDINATE_CONFIG_FILENAME",
    "SCAN_CONFIG_FILENAME",
]

"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.library.circuit_id_mapping import (
    annotations,
    find_stale_populations,
    get_population_sizes,
    json,
    L,
    libsonata,
    logging,
    TYPE_CHECKING,
    validate_id_mapping_files,
)

__all__ = [
    "annotations",
    "find_stale_populations",
    "get_population_sizes",
    "json",
    "L",
    "libsonata",
    "logging",
    "TYPE_CHECKING",
    "validate_id_mapping_files",
]

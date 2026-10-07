"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.library.morphology_loader import (
    load_morphology_nrn_order,
    load_morphology_nrn_order_from_collection,
    morphio,
    Path,
)

__all__ = [
    "load_morphology_nrn_order",
    "load_morphology_nrn_order_from_collection",
    "morphio",
    "Path",
]

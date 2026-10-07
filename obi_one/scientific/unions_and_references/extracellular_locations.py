"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.unions_and_references.extracellular_locations import (
    Annotated,
    Any,
    BlockReference,
    ClassVar,
    Discriminator,
    ExtracellularLocationsReference,
    ExtracellularLocationsUnion,
    GridExtracellularLocations,
    LinearExtracellularLocations,
    Neuropixels1ExtracellularLocations,
    UTAHArrayExtracellularLocations,
)

from obi_one_lazy.scientific.unions_and_references.extracellular_locations import (
    _EXTRACELLULAR_LOCATION_BLOCKS,
)

__all__ = [
    "Annotated",
    "Any",
    "BlockReference",
    "ClassVar",
    "Discriminator",
    "ExtracellularLocationsReference",
    "ExtracellularLocationsUnion",
    "GridExtracellularLocations",
    "LinearExtracellularLocations",
    "Neuropixels1ExtracellularLocations",
    "UTAHArrayExtracellularLocations",
    "_EXTRACELLULAR_LOCATION_BLOCKS",
]

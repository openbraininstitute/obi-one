"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.unions_and_references.morphology_locations import (
    Annotated,
    Any,
    BlockReference,
    CircuitMorphologyLocationUnion,
    ClassVar,
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    Discriminator,
    ExplicitMorphologyLocations,
    get_args,
    MorphologyLocationsReference,
    MorphologyLocationUnion,
    PathDistanceMorphologyLocations,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)

from obi_one_lazy.scientific.unions_and_references.morphology_locations import (
    _ALL_MORPHOLOGY_LOCATIONS,
    _GENERATED_MORPHOLOGY_LOCATIONS,
)

__all__ = [
    "Annotated",
    "Any",
    "BlockReference",
    "CircuitMorphologyLocationUnion",
    "ClassVar",
    "ClusteredGroupedMorphologyLocations",
    "ClusteredMorphologyLocations",
    "ClusteredPathDistanceMorphologyLocations",
    "Discriminator",
    "ExplicitMorphologyLocations",
    "get_args",
    "MorphologyLocationsReference",
    "MorphologyLocationUnion",
    "PathDistanceMorphologyLocations",
    "RandomGroupedMorphologyLocations",
    "RandomMorphologyLocations",
    "_ALL_MORPHOLOGY_LOCATIONS",
    "_GENERATED_MORPHOLOGY_LOCATIONS",
]

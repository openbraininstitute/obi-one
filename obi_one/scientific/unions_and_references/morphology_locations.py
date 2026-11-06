from typing import Annotated, Any, ClassVar, get_args

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.explicit import ExplicitMorphologyLocations
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)

# Locations sampled across the morphologies of a targeted neuron set. Every neuron receives its
# own sampled locations, so a section id always refers to the morphology it was sampled on.
_GENERATED_MORPHOLOGY_LOCATIONS = (
    ClusteredGroupedMorphologyLocations
    | ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | PathDistanceMorphologyLocations
    | RandomGroupedMorphologyLocations
    | RandomMorphologyLocations
)

_ALL_MORPHOLOGY_LOCATIONS = _GENERATED_MORPHOLOGY_LOCATIONS | ExplicitMorphologyLocations

MorphologyLocationUnion = Annotated[
    _ALL_MORPHOLOGY_LOCATIONS,
    Discriminator("type"),
]

# Explicit locations name a section and offset but no cell, so on a multi-neuron circuit the same
# branch id means a different branch on every morphology. They are therefore offered only for
# single-neuron configurations.
CircuitMorphologyLocationUnion = Annotated[
    _GENERATED_MORPHOLOGY_LOCATIONS,
    Discriminator("type"),
]


# Locations that are neither explicit (they name a section/offset but no cell, so they do not
# transfer between morphologies) nor grouped (grouping assigns locations to distinct presynaptic
# neurons, which is not meaningful when the presynaptic side is defined by a connectivity model).
# Clustered locations are allowed.
_NON_GROUPED_MORPHOLOGY_LOCATIONS = (
    ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | PathDistanceMorphologyLocations
    | RandomMorphologyLocations
)

NonGroupedMorphologyLocationUnion = Annotated[
    _NON_GROUPED_MORPHOLOGY_LOCATIONS,
    Discriminator("type"),
]


class NonGroupedMorphologyLocationsReference(BlockReference):
    """Reference to a block that generates non-grouped, non-explicit morphology locations."""

    allowed_block_types: ClassVar[Any] = NonGroupedMorphologyLocationUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_NON_GROUPED_MORPHOLOGY_LOCATIONS)
    }


class MorphologyLocationsReference(BlockReference):
    """Reference to a block that generates morphology locations."""

    allowed_block_types: ClassVar[Any] = MorphologyLocationUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(get_args(MorphologyLocationUnion)[0])
    }


__all__ = [
    "CircuitMorphologyLocationUnion",
    "MorphologyLocationUnion",
    "MorphologyLocationsReference",
    "NonGroupedMorphologyLocationUnion",
    "NonGroupedMorphologyLocationsReference",
]

from typing import Annotated, Any, ClassVar, get_args

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.explicit import ExplicitMorphologyLocations
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomMorphologyLocations,
)

# Locations sampled across the morphologies of a targeted neuron set. Every neuron in the set
# receives its own sampled locations, so these work on a circuit of any size.
_GENERATED_MORPHOLOGY_LOCATIONS = (
    ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | PathDistanceMorphologyLocations
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
]

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
from obi_one.scientific.blocks.morphology_locations.per_neuron_explicit import (
    PerNeuronExplicitMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomMorphologyLocations,
)

# Locations sampled across the morphologies of a targeted neuron set. Every neuron receives its
# own sampled locations, so a section id always refers to the morphology it was sampled on.
_GENERATED_MORPHOLOGY_LOCATIONS = (
    ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | PathDistanceMorphologyLocations
    | RandomMorphologyLocations
)

# Per-neuron explicit locations each name their own neuron, so unlike plain explicit locations
# they are unambiguous on a multi-neuron circuit and can join the sampled blocks here.
_CIRCUIT_MORPHOLOGY_LOCATIONS = (
    _GENERATED_MORPHOLOGY_LOCATIONS | PerNeuronExplicitMorphologyLocations
)

_ALL_MORPHOLOGY_LOCATIONS = _CIRCUIT_MORPHOLOGY_LOCATIONS | ExplicitMorphologyLocations

MorphologyLocationUnion = Annotated[
    _ALL_MORPHOLOGY_LOCATIONS,
    Discriminator("type"),
]

# Blocks that sample points on a single morphology, i.e. implement `points_on`. Per-neuron
# explicit locations are excluded: their rows already name a node id each, so there is no single
# morphology to sample against.
SingleMorphologySamplingLocationUnion = Annotated[
    _GENERATED_MORPHOLOGY_LOCATIONS | ExplicitMorphologyLocations,
    Discriminator("type"),
]

# Plain explicit locations name a section and offset but no cell, so on a multi-neuron circuit the
# same branch id means a different branch on every morphology. They are therefore offered only for
# single-neuron configurations.
CircuitMorphologyLocationUnion = Annotated[
    _CIRCUIT_MORPHOLOGY_LOCATIONS,
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
    "SingleMorphologySamplingLocationUnion",
]

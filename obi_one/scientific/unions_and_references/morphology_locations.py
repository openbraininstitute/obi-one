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

MorphologyLocationUnion = Annotated[
    ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | ExplicitMorphologyLocations
    | PathDistanceMorphologyLocations
    | RandomMorphologyLocations,
    Discriminator("type"),
]


class MorphologyLocationsReference(BlockReference):
    """Reference to a block that generates morphology locations.

    No `title` override here. `OBIBaseModel.__init_subclass__` promotes `title` to the
    JSON-schema title, and the frontend keys its allowed-block-types registry on that title
    while looking entries up by the class names carried in `reference_types`. A display
    title breaks that join, and the morphology-location options silently disappear from
    every field that also accepts neuron sets.
    """

    allowed_block_types: ClassVar[Any] = MorphologyLocationUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(get_args(MorphologyLocationUnion)[0])
    }


__all__ = ["MorphologyLocationUnion", "MorphologyLocationsReference"]

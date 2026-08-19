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
    """Reference to a block that generates morphology locations."""

    title: ClassVar[str] = "Morphology Locations Reference"
    allowed_block_types: ClassVar[Any] = MorphologyLocationUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(get_args(MorphologyLocationUnion)[0])
    }


__all__ = ["MorphologyLocationUnion", "MorphologyLocationsReference"]

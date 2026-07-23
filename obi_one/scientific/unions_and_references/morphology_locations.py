from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.morphology_locations.clustered import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.path_distance import (
    PathDistanceMorphologyLocations,
)
from obi_one.scientific.blocks.morphology_locations.random import (
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)

MorphologyLocationUnion = Annotated[
    ClusteredGroupedMorphologyLocations
    | ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | PathDistanceMorphologyLocations
    | RandomGroupedMorphologyLocations
    | RandomMorphologyLocations,
    Discriminator("type"),
]


class MorphologyLocationsReference(BlockReference):
    """Reference to a block that generates morphology locations."""

    allowed_block_types: ClassVar[Any] = MorphologyLocationUnion


__all__ = ["MorphologyLocationUnion", "MorphologyLocationsReference"]

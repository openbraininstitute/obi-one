from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.morphology_locations import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    MorphologyLocationsBlock,
    PathDistanceMorphologyLocations,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)

MorphologyLocationUnion = Annotated[
    ClusteredGroupedMorphologyLocations
    | ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | MorphologyLocationsBlock
    | PathDistanceMorphologyLocations
    | RandomGroupedMorphologyLocations
    | RandomMorphologyLocations,
    Discriminator("type"),
]

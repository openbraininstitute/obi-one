from obi_one.scientific.morphology_locations import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    MorphologyLocationsBlock,
    PathDistanceMorphologyLocations,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)

# MorphologyLocationUnion = (
#     MorphologyLocationsBlock
#     | RandomGroupedMorphologyLocations
#     | RandomMorphologyLocations
#     | ClusteredGroupedMorphologyLocations
#     | ClusteredMorphologyLocations
#     | ClusteredPathDistanceMorphologyLocations
#     | PathDistanceMorphologyLocations
# )

from pydantic import Field
from typing import Union, Annotated
MorphologyLocationUnion = Annotated[Union[(
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    MorphologyLocationsBlock,
    PathDistanceMorphologyLocations,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)], Field(discriminator='type')]
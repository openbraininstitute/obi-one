from obi_one.scientific.morphology_locations import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    MorphologyLocationsBlock,
    PathDistanceMorphologyLocations,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)

from pydantic import Field, Discriminator
from typing import Union, Annotated
MorphologyLocationUnion = Annotated[Union[(
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    MorphologyLocationsBlock,
    PathDistanceMorphologyLocations,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)], Discriminator('type')]
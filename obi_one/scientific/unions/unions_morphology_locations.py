from obi_one.scientific.morphology_locations import (
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    MorphologyLocationsBlock,
    PathDistanceMorphologyLocations,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
)

MorphologyLocationUnion = (
    MorphologyLocationsBlock
    | RandomGroupedMorphologyLocations
    | RandomMorphologyLocations
    | ClusteredGroupedMorphologyLocations
    | ClusteredMorphologyLocations
    | ClusteredPathDistanceMorphologyLocations
    | PathDistanceMorphologyLocations
)

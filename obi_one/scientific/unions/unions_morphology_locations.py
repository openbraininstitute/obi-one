from obi_one.scientific.morphology_locations import (
    MorphologyLocationsBlock,
    RandomGroupedMorphologyLocations,
    RandomMorphologyLocations,
    ClusteredGroupedMorphologyLocations,
    ClusteredMorphologyLocations,
    ClusteredPathDistanceMorphologyLocations,
    PathDistanceMorphologyLocations
)

MorphologyLocationUnion = (
    MorphologyLocationsBlock |
    RandomGroupedMorphologyLocations |
    RandomMorphologyLocations | 
    ClusteredGroupedMorphologyLocations | 
    ClusteredMorphologyLocations |
    ClusteredPathDistanceMorphologyLocations |
    PathDistanceMorphologyLocations
)
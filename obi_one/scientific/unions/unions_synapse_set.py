from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.blocks.afferent_synapses import (
    AfferentSynapsesBlock,
    ClusteredPDSynapsesByCount,
    ClusteredPDSynapsesByMaxDistance,
    ClusteredSynapsesByCount,
    ClusteredSynapsesByMaxDistance,
    PathDistanceConstrainedFractionOfSynapses,
    PathDistanceConstrainedNumberOfSynapses,
    PathDistanceWeightedFractionOfSynapses,
    PathDistanceWeightedNumberOfSynapses,
    RandomlySelectedFractionOfSynapses,
    RandomlySelectedNumberOfSynapses,
)

SynapseSetUnion = Annotated[
    AfferentSynapsesBlock
    | ClusteredPDSynapsesByCount
    | ClusteredPDSynapsesByMaxDistance
    | ClusteredSynapsesByCount
    | ClusteredSynapsesByMaxDistance
    | PathDistanceConstrainedFractionOfSynapses
    | PathDistanceConstrainedNumberOfSynapses
    | PathDistanceWeightedFractionOfSynapses
    | PathDistanceWeightedNumberOfSynapses
    | RandomlySelectedFractionOfSynapses
    | RandomlySelectedNumberOfSynapses,
    Discriminator("type"),
]

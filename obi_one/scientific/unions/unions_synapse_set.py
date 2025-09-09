from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.afferent_synapse_finder.specified_afferent_synapses_block import (
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

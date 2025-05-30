from obi_one.scientific.afferent_synapse_finder.specified_afferent_synapses_block import (
    AfferentSynapsesBlock,
    RandomlySelectedFractionOfSynapses,
    RandomlySelectedNumberOfSynapses,
    ClusteredSynapsesByCount,
    ClusteredSynapsesByMaxDistance,
    ClusteredPDSynapsesByMaxDistance,
    ClusteredPDSynapsesByCount,
    PathDistanceWeightedNumberOfSynapses,
    PathDistanceWeightedFractionOfSynapses,
    PathDistanceConstrainedNumberOfSynapses,
    PathDistanceConstrainedFractionOfSynapses
)

SynapseSetUnion = (
    AfferentSynapsesBlock |
    RandomlySelectedFractionOfSynapses |
    RandomlySelectedNumberOfSynapses |
    PathDistanceConstrainedFractionOfSynapses |
    PathDistanceConstrainedNumberOfSynapses |
    PathDistanceWeightedFractionOfSynapses |
    PathDistanceWeightedNumberOfSynapses |
    ClusteredPDSynapsesByCount |
    ClusteredPDSynapsesByMaxDistance |
    ClusteredSynapsesByCount |
    ClusteredSynapsesByMaxDistance
)

from obi_one.scientific.circuit.synapse_sets import (
    IDSynapseSet,
)
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

SynapseSetUnion = IDSynapseSet

AfferentSynapseSetUnion = (
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

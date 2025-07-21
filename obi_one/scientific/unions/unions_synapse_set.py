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

# SynapseSetUnion = (
#     AfferentSynapsesBlock
#     | RandomlySelectedFractionOfSynapses
#     | RandomlySelectedNumberOfSynapses
#     | PathDistanceConstrainedFractionOfSynapses
#     | PathDistanceConstrainedNumberOfSynapses
#     | PathDistanceWeightedFractionOfSynapses
#     | PathDistanceWeightedNumberOfSynapses
#     | ClusteredPDSynapsesByCount
#     | ClusteredPDSynapsesByMaxDistance
#     | ClusteredSynapsesByCount
#     | ClusteredSynapsesByMaxDistance
# )

from pydantic import Field
from typing import Union, Annotated
SynapseSetUnion = Annotated[Union[(
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
)], Field(discriminator='type')]

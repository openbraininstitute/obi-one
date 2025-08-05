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

from pydantic import Field, Discriminator
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
)], Discriminator('type')]

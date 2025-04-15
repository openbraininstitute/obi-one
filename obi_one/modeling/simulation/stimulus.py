from obi_one.modeling.core.block import Block

from obi_one.modeling.unions.unions_timestamps import TimestampsUnion
from obi_one.modeling.unions.unions_synapse_set import SynapseSetUnion

class Stimulus(Block):
    synapse_set: SynapseSetUnion
    timestamps: TimestampsUnion

class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
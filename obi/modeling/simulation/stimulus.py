# from typing import Union, List

from obi.modeling.core.block import Block
from obi.modeling.circuit.synapse_sets import SynapseSet
from obi.modeling.simulation.timestamps import Timestamps

from obi.modeling.unions.unions_timestamps import TimestampsUnion

class Stimulus(Block):
    synapse_set: SynapseSet
    timestamps: TimestampsUnion

class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
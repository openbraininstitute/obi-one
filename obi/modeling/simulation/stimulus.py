from typing import Union, List

from obi.modeling.core.block import Block
from obi.modeling.circuit.synapse_sets import SynapseSet
from obi.modeling.simulation.timestamps import Timestamps

class Stimulus(Block):
    synapse_set: SynapseSet
    timestamps: Timestamps

class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
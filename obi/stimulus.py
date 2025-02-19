from .template import SubTemplate
from typing import Union, List

    
from .timestamps import Timestamps
from .synapse_sets import SynapseSet

class Stimulus(SubTemplate):
    synapse_set: SynapseSet
    timestamps: Timestamps

class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
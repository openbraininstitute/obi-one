from typing import Union, List

from ..core.template import SubTemplate
from ..circuit.synapse_sets import SynapseSet
from .timestamps import Timestamps

class Stimulus(SubTemplate):
    synapse_set: SynapseSet
    timestamps: Timestamps

class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
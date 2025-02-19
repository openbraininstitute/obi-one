from .template import SubTemplate
from typing import Union, List

    
from .timestamps import Timestamps
from .circuit_grouping import CircuitGrouping

class Stimulus(SubTemplate):
    circuit_grouping: CircuitGrouping
    timestamps: Timestamps

class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
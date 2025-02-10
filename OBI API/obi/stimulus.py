from .multi_template import MultiTemplate
from .timestamps import Timestamps
from .circuit_grouping import CircuitGrouping

class Stimulus(MultiTemplate):
    circuit_grouping: CircuitGrouping
    timestamps: Timestamps

class SynchronousSingleSpikeStimulus(Stimulus):
    spike_probability: float | list[float]
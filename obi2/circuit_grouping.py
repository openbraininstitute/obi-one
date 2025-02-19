from .template import SubTemplate
from .circuit import Circuit

class CircuitGrouping(SubTemplate):
    circuit: Circuit

class NeuronCircuitGrouping(CircuitGrouping):
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
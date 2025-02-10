from .multi_template import MultiTemplate
from .circuit import Circuit

class CircuitGrouping(MultiTemplate):
    circuit: Circuit

class NeuronCircuitGrouping(CircuitGrouping):
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
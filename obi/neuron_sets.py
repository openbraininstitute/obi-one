from .template import SubTemplate
from .circuit import Circuit

class NeuronSet(SubTemplate):
    """
    """
    circuit: Circuit

class IDNeuronSet(NeuronSet):
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
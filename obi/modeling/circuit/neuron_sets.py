from ..core.template import Block
from ..circuit.circuit import Circuit

class NeuronSet(Block):
    """
    """
    circuit: Circuit

class IDNeuronSet(NeuronSet):
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
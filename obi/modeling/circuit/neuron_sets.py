from obi.modeling.core.block import Block
from obi.modeling.circuit.circuit import Circuit

class NeuronSet(Block):
    """
    """
    circuit: Circuit

class IDNeuronSet(NeuronSet):
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
from obi_one.core.block import Block
from obi_one.scientific.circuit.circuit import Circuit

class NeuronSet(Block):
    """
    """
    circuit: Circuit

class IDNeuronSet(NeuronSet):
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
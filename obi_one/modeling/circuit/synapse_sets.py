from obi_one.modeling.core.block import Block
from obi_one.modeling.circuit.circuit import Circuit

class SynapseSet(Block):
    """
    """
    circuit: Circuit

class IDSynapseSet(SynapseSet):
    synapse_ids: tuple[int, ...] | list[tuple[int, ...]]
from obi.modeling.core.block import Block
from obi.modeling.circuit.circuit import Circuit

class SynapseSet(Block):
    """
    """
    circuit: Circuit

class IDSynapseSet(SynapseSet):
    synapse_ids: tuple[int, ...] | list[tuple[int, ...]]
from ..core.template import Block
from ..circuit.circuit import Circuit

class SynapseSet(Block):
    """
    """
    circuit: Circuit

class IDSynapseSet(SynapseSet):
    synapse_ids: tuple[int, ...] | list[tuple[int, ...]]
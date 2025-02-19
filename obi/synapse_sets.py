from .template import SubTemplate
from .circuit import Circuit

class SynapseSet(SubTemplate):
    """
    """
    circuit: Circuit

class IDSynapseSet(SynapseSet):
    synapse_ids: tuple[int, ...] | list[tuple[int, ...]]
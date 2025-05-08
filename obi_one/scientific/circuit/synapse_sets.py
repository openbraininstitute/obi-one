from obi_one.core.block import Block
from obi_one.scientific.circuit.circuit import Circuit


class SynapseSet(Block):
    """ """

    circuit: Circuit


class IDSynapseSet(SynapseSet):
    synapse_ids: tuple[int, ...] | list[tuple[int, ...]]

from ..core.template import Block
from ..circuit.circuit import Circuit

class IntracellularLocationSet(Block):
    """
    """
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
    section: str

# class IDSectionIntracellularLocationSet(IntracellularLocationSet):
#     neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
#     section: str
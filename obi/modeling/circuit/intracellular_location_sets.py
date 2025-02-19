from ..core.template import SubTemplate
from ..circuit.circuit import Circuit

class IntracellularLocationSet(SubTemplate):
    """
    """
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
    section: str

# class IDSectionIntracellularLocationSet(IntracellularLocationSet):
#     neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
#     section: str
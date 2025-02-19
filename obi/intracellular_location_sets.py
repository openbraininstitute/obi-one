from .template import SubTemplate
from .circuit import Circuit

class IntracellularLocationSet(SubTemplate):
    """
    """

class SomaIntracellularLocationSet(IntracellularLocationSet):
    neuron_ids: tuple[int, ...] | list[tuple[int, ...]]
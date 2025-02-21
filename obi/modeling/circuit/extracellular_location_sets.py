from ..core.form import Block
from ..circuit.circuit import Circuit

class ExtracellularLocationSet(Block):
    """
    """

class XYZExtracellularLocationSet(ExtracellularLocationSet):
    xyz_locations: tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
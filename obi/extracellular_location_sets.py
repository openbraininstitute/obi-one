from .template import SubTemplate
from .circuit import Circuit

class ExtracellularLocationSet(SubTemplate):
    """
    """

class XYZExtracellularLocationSet(ExtracellularLocationSet):
    xyz_locations: tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
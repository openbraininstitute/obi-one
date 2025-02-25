from obi.modeling.core.block import Block

class ExtracellularLocationSet(Block):
    """
    """

class XYZExtracellularLocationSet(ExtracellularLocationSet):
    xyz_locations: tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
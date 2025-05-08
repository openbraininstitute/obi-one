from obi_one.core.block import Block


class ExtracellularLocationSet(Block):
    """ """


class XYZExtracellularLocationSet(ExtracellularLocationSet):
    xyz_locations: (
        tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
    ) = ((0.0, 0.0, 0.0),)

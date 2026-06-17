from obi_one.core.block import Block


class ExtracellularLocations(Block):
    """Base class of extracellular locations."""


class XYZExtracellularLocations(ExtracellularLocations):
    xyz_locations: (
        tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
    ) = ((0.0, 0.0, 0.0),)

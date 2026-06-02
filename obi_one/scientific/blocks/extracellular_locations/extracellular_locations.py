from abc import ABC

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement


class ExtracellularLocations(Block):
    """Base class of extracellular locations."""


class XYZExtracellularLocations(ExtracellularLocations):
    xyz_locations: (
        tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
    ) = ((0.0, 0.0, 0.0),)


class PatternedExtracellularLocations(ExtracellularLocations, ABC):
    """Base class for patterned extracellular locations.

    The locations are determined by a specific pattern and parameters.
    """

    origin_x: float | list[float] = Field(
        default=0.0,
        title="Origin X",
        description="X coordinate of the origin point for the electrode array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    origin_y: float | list[float] = Field(
        default=0.0,
        title="Origin Y",
        description="Y coordinate of the origin point for the electrode array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    origin_z: float | list[float] = Field(
        default=0.0,
        title="Origin Z",
        description="Z coordinate of the origin point for the electrode array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    direction_x: float | list[float] = Field(
        default=0.0,
        title="Direction X",
        description="X component of the direction vector for the electrode array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    direction_y: float | list[float] = Field(
        default=1.0,
        title="Direction Y",
        description="Y component of the direction vector for the electrode array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    direction_z: float | list[float] = Field(
        default=0.0,
        title="Direction Z",
        description="Z component of the direction vector for the electrode array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def get_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Calculate the XYZ locations of the electrodes based on the pattern parameters."""
        msg = "Subclasses of must implement get_xyz_locations method."
        raise NotImplementedError(msg)

    def xyz_locations_with_origin_and_direction_applied(self) -> list[tuple[float, float, float]]:
        """Calculate the XYZ locations of the electrodes based on the origin and direction."""
        initial_xyz_locations = self.get_xyz_locations()
        xyz_locations = []

        unit_direction_x = (
            self.direction_x
            / (self.direction_x**2 + self.direction_y**2 + self.direction_z**2) ** 0.5  # ty:ignore[unsupported-operator]
        )
        unit_direction_y = (
            self.direction_y
            / (self.direction_x**2 + self.direction_y**2 + self.direction_z**2) ** 0.5  # ty:ignore[unsupported-operator]
        )
        unit_direction_z = (
            self.direction_z
            / (self.direction_x**2 + self.direction_y**2 + self.direction_z**2) ** 0.5  # ty:ignore[unsupported-operator]
        )

        for x, y, z in initial_xyz_locations:
            new_x = self.origin_x + (x * unit_direction_x)
            new_y = self.origin_y + (y * unit_direction_y)
            new_z = self.origin_z + (z * unit_direction_z)
            xyz_locations.append((new_x, new_y, new_z))
        return xyz_locations


class LinearExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations arranged in a linear pattern."""

    n_electrodes: int | list[int] = Field(
        default=16,
        title="Number of Electrodes",
        description="Number of electrodes in the linear array.",
        ge=1,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    spacing: float | list[float] = Field(
        default=20.0,
        title="Spacing",
        description="Spacing between electrodes in micrometers.",
        gt=0.0,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def get_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Calculate the XYZ locations of the electrodes based on electrode count and spacing."""
        xyz_locations = []
        for electrode_i in range(self.n_electrodes):  # ty:ignore[invalid-argument-type]
            x = self.origin_x + (electrode_i * self.spacing)  # ty:ignore[unsupported-operator]
            y = self.origin_y + (electrode_i * self.spacing)  # ty:ignore[unsupported-operator]
            z = self.origin_z + (electrode_i * self.spacing)  # ty:ignore[unsupported-operator]
            xyz_locations.append((x, y, z))
        return xyz_locations


class Neuropixels1ExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations for Neuropixels 1.0 probe."""

    n_electrodes: int | list[int] = Field(
        default=384,
        title="Number of Electrodes",
        description="Number of electrodes in the Neuropixels 1.0 probe.",
        ge=1,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def get_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Calculate the XYZ locations of the electrodes based on vertical repetitions."""
        # Neuropixels 1.0 probe has a specific pattern of electrode locations.
        # For simplicity, we will assume a linear arrangement with a fixed spacing.
        vertical_spacing = 20.0  # micrometers
        horizontal_spacing = 16.0  # micrometers
        alternate_horizontal_stride = horizontal_spacing

        xyz_locations = []
        for electrode_i in range(self.n_electrodes):  # ty:ignore[invalid-argument-type]
            horizontal_position = electrode_i % 2
            x = self.origin_x + (horizontal_position * horizontal_spacing)  # ty:ignore[unsupported-operator]
            # Every 2nd pair of electrodes, the horizontal position shifts by an additional stride
            if electrode_i % 4 in {2, 3}:
                x += alternate_horizontal_stride

            vertical_position = electrode_i % (self.n_electrodes // 2)  # ty:ignore[unsupported-operator]
            y = self.origin_y + (vertical_position * vertical_spacing)

            z = self.origin_z

            xyz_locations.append((x, y, z))

        return xyz_locations

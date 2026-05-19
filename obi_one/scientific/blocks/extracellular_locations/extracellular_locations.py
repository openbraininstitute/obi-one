from importlib import abc

from pydantic import Field

from obi_one.core.block import Block

from obi_one.core.schema import SchemaKey, UIElement


class ExtracellularLocations(Block):
    """Base class of extracellular locations."""


class XYZExtracellularLocations(ExtracellularLocations):
    xyz_locations: (
        tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
    ) = ((0.0, 0.0, 0.0),)

class PatternedExtracellularLocations(ExtracellularLocations, abc.ABC):
    """Base class for patterned extracellular locations, where the locations are determined by a specific pattern and parameters."""

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

    def xyz_locations_with_origin_and_direction_applied(self) -> list[tuple[float, float, float]]:
        """Calculate the XYZ locations of the electrodes based on the origin and direction."""
        
        initial_xyz_locations = self.get_xyz_locations()
        xyz_locations = []

        unit_direction_x = self.direction_x / (self.direction_x**2 + self.direction_y**2 + self.direction_z**2) ** 0.5
        unit_direction_y = self.direction_y / (self.direction_x**2 + self.direction_y**2 + self.direction_z**2) ** 0.5
        unit_direction_z = self.direction_z / (self.direction_x**2 + self.direction_y**2 + self.direction_z**2) ** 0.5

        for x, y, z in initial_xyz_locations:
            x = self.origin_x + (x * unit_direction_x)
            y = self.origin_y + (y * unit_direction_y)
            z = self.origin_z + (z * unit_direction_z)
            xyz_locations.append((x, y, z))
        return xyz_locations

class LinearExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations arranged in a linear pattern."""

    n_electrodes: int | list[int] = Field(
        default=16,
        title="Number of Electrodes",
        description="Number of electrodes in the linear array.",
        ge=1,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INTEGER_PARAMETER_SWEEP,
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
        """Calculate the XYZ locations of the electrodes based on the number of electrodes and spacing."""
        xyz_locations = []
        for electrode_i in range(self.n_electrodes):
            x = self.origin_x + (electrode_i * self.spacing)
            y = self.origin_y + (electrode_i * self.spacing)
            z = self.origin_z + (electrode_i * self.spacing)
            xyz_locations.append((x, y, z))
        return xyz_locations


class Neuropixels1_0ExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations for Neuropixels 1.0 probe."""

    n_electrodes: int | list[int] = Field(
        default=384,
        title="Number of Electrodes",
        description="Number of electrodes in the Neuropixels 1.0 probe.",
        ge=1,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INTEGER_PARAMETER_SWEEP,
        },
    )

    def get_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Calculate the XYZ locations of the electrodes based on the number of vertical repetitions."""
        # Neuropixels 1.0 probe has a specific pattern of electrode locations.
        # For simplicity, we will assume a linear arrangement with a fixed spacing.
        vertical_spacing = 20.0  # micrometers
        horizontal_spacing = 16.0  # micrometers
        alternate_horizontal_stride = horizontal_spacing
        n_electrodes = 384  # Total number of electrodes in Neuropixels 1.0 probe

        xyz_locations = []
        for electrode_i in range(self.n_electrodes):

            horizontal_position = electrode_i % 2
            x = self.origin_x + (horizontal_position * horizontal_spacing)
            if electrode_i % 4 in [2, 3]:  # Every 2nd pair of electrodes, the horizontal position shifts by an additional stride
                x += alternate_horizontal_stride

            vertical_position = electrode_i % (self.n_electrodes // 2)
            y = self.origin_y + (vertical_position * vertical_spacing)

            z = self.origin_z

            xyz_locations.append((x, y, z))
        
        return xyz_locations
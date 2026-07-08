import math
from abc import ABC
from typing import Annotated, Self

from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units

# If the array direction is (anti-)parallel to the reference axis used to construct the
# electrode plane, the cross product degenerates; fall back to a different reference axis.
_DIRECTION_PARALLEL_TOLERANCE = 0.999


def _cross(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Return the cross product ``a x b`` of two 3-vectors."""
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


class ExtracellularLocations(Block):
    """Base class of extracellular locations."""


class XYZExtracellularLocations(ExtracellularLocations):
    xyz_locations: (
        tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
    ) = ((0.0, 0.0, 0.0),)


class PatternedExtracellularLocations(ExtracellularLocations, ABC):
    """Base class for patterned extracellular locations.

    The locations are determined by a specific pattern and parameters. Subclasses define the
    pattern in a *local* frame via :meth:`get_local_electrode_xyz_locations` (origin at
    ``(0, 0, 0)`` with the array running along the local ``+Y`` axis). That pattern is then
    rigidly placed into world space by rotating the local ``+Y`` axis onto ``direction`` and
    translating by ``origin`` (see :meth:`get_global_electrode_xyz_locations`).
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

    @model_validator(mode="after")
    def _reject_zero_direction(self) -> Self:
        """Reject a zero direction vector: it gives no orientation to place the array along.

        Each component may be a scalar or a parameter-sweep list, so the zero vector is reachable
        only when zero appears among the values of all three components.
        """
        components = (self.direction_x, self.direction_y, self.direction_z)
        zero_reachable = [
            0.0 in (values if isinstance(values, list) else [values]) for values in components
        ]
        if all(zero_reachable):
            msg = "direction_x, direction_y and direction_z must not all be zero."
            raise ValueError(msg)
        return self

    def get_local_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return the electrode locations in the array's local frame.

        The local frame has its origin at ``(0, 0, 0)`` with the array running along the ``+Y``
        axis; ``origin`` and ``direction`` are *not* applied here (see
        :meth:`get_global_electrode_xyz_locations`).
        """
        msg = "Subclasses must implement get_local_electrode_xyz_locations()."
        raise NotImplementedError(msg)

    def get_global_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return the electrode locations in world coordinates.

        The local pattern from :meth:`get_local_electrode_xyz_locations` is rigidly transformed
        into world space: its local ``+Y`` axis is rotated onto the (normalised) ``direction``
        vector and its local origin is translated to ``origin``. For the default ``direction`` of
        ``(0, 1, 0)`` this reduces to a pure translation by ``origin``.
        """
        # These methods are only meaningful on single (expanded) configs, where every parameter
        # is a scalar rather than a parameter-sweep list.
        origin_x = float(self.origin_x)  # ty:ignore[invalid-argument-type]
        origin_y = float(self.origin_y)  # ty:ignore[invalid-argument-type]
        origin_z = float(self.origin_z)  # ty:ignore[invalid-argument-type]
        direction_x = float(self.direction_x)  # ty:ignore[invalid-argument-type]
        direction_y = float(self.direction_y)  # ty:ignore[invalid-argument-type]
        direction_z = float(self.direction_z)  # ty:ignore[invalid-argument-type]

        direction_norm = (direction_x**2 + direction_y**2 + direction_z**2) ** 0.5
        if direction_norm <= 0.0:  # a norm is non-negative, so this catches the zero vector
            msg = "Direction vector must be non-zero."
            raise ValueError(msg)
        forward = (
            direction_x / direction_norm,
            direction_y / direction_norm,
            direction_z / direction_norm,
        )

        # Build an orthonormal basis (right, forward, out) mapping the local (X, +Y, Z) axes into
        # world space. Pick a reference axis that is not (anti-)parallel to `forward`.
        reference = (0.0, 0.0, 1.0)
        if abs(forward[2]) > _DIRECTION_PARALLEL_TOLERANCE:
            reference = (1.0, 0.0, 0.0)

        right = _cross(forward, reference)
        right_norm = (right[0] ** 2 + right[1] ** 2 + right[2] ** 2) ** 0.5
        right = (right[0] / right_norm, right[1] / right_norm, right[2] / right_norm)
        out = _cross(right, forward)

        world_locations = []
        for local_x, local_y, local_z in self.get_local_electrode_xyz_locations():
            world_locations.append(
                (
                    origin_x + local_x * right[0] + local_y * forward[0] + local_z * out[0],
                    origin_y + local_x * right[1] + local_y * forward[1] + local_z * out[1],
                    origin_z + local_x * right[2] + local_y * forward[2] + local_z * out[2],
                )
            )
        return world_locations


class LinearExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations arranged in a linear pattern."""

    n_electrodes: Annotated[int, Field(ge=1)] | list[Annotated[int, Field(ge=1)]] = Field(
        default=16,
        title="Number of Electrodes",
        description="Number of electrodes in the linear array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    spacing: Annotated[float, Field(gt=0.0)] | list[Annotated[float, Field(gt=0.0)]] = Field(
        default=20.0,
        title="Spacing",
        description="Spacing between electrodes in micrometers.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def get_local_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return electrodes evenly spaced along the local ``+Y`` axis."""
        n_electrodes = int(self.n_electrodes)  # ty:ignore[invalid-argument-type]
        spacing = float(self.spacing)  # ty:ignore[invalid-argument-type]
        return [(0.0, electrode_i * spacing, 0.0) for electrode_i in range(n_electrodes)]


class Neuropixels1ExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations for Neuropixels 1.0 probe."""

    n_electrodes: Annotated[int, Field(ge=1)] | list[Annotated[int, Field(ge=1)]] = Field(
        default=384,
        title="Number of Electrodes",
        description="Number of electrodes in the Neuropixels 1.0 probe.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    axial_rotation: (
        Annotated[float, Field(ge=0.0, le=360.0)] | list[Annotated[float, Field(ge=0.0, le=360.0)]]
    ) = Field(
        default=0.0,
        title="Axial Rotation",
        description=(
            "Rotation of the probe about its long axis (the origin/direction line), in degrees. "
            "At 0 the electrode columns lie in the local X-Y plane; increasing it rolls the "
            "shank's width out of that plane into local Z."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )

    def get_local_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return Neuropixels 1.0 electrodes in the local frame (staggered layout).

        Matches the imec Neuropixels 1.0 geometry: two sites per row 32 um apart, rows 20 um apart,
        with alternate rows offset by a 16 um stagger (four columns at a 16 um pitch). The pattern
        is centred on the local ``+Y`` (long) axis so ``origin`` is the centre of the top of the
        shank, then rolled about that axis by ``axial_rotation`` degrees into local Z.
        """
        row_pitch = 20.0  # vertical spacing between rows (electrode_pitch_vert_um)
        within_row_spacing = 32.0  # horizontal spacing between the two sites in a row (horz pitch)
        row_stagger = 16.0  # horizontal offset applied to alternate rows
        # X of the shank-width centre, so `origin` sits at the centre rather than an edge.
        horizontal_centre = (within_row_spacing + row_stagger) / 2.0

        n_electrodes = int(self.n_electrodes)  # ty:ignore[invalid-argument-type]
        roll = math.radians(float(self.axial_rotation))  # ty:ignore[invalid-argument-type]
        cos_roll = math.cos(roll)
        sin_roll = math.sin(roll)

        xyz_locations = []
        for electrode_i in range(n_electrodes):
            row = electrode_i // 2  # two sites share each row
            column = electrode_i % 2  # 0 or 1 within the row
            # Centre the staggered width on the local +Y axis so the origin is at the centre-top.
            x = column * within_row_spacing + (row % 2) * row_stagger - horizontal_centre
            y = row * row_pitch

            # Roll the (centred) width offset about the local +Y axis into local Z.
            xyz_locations.append((x * cos_roll, y, -x * sin_roll))

        return xyz_locations


class UtahArrayExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations for a classic Utah array.

    The Utah array (Blackrock Microsystems) is a square grid of penetrating micro-electrodes: the
    classic device is a 10x10 grid on a 400 um pitch whose recording sites sit at the tips of
    uniform-length silicon shanks. In the local frame the shanks run along the ``+Y`` (insertion)
    axis, so the tips form the grid in the local X-Z plane at ``+Y = shank_length``, centred on the
    ``+Y`` axis; ``origin`` is then the centre of the array base and ``direction`` the insertion
    direction.
    """

    grid_rows: Annotated[int, Field(ge=1)] | list[Annotated[int, Field(ge=1)]] = Field(
        default=10,
        title="Grid Rows",
        description="Number of electrode rows in the array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    grid_columns: Annotated[int, Field(ge=1)] | list[Annotated[int, Field(ge=1)]] = Field(
        default=10,
        title="Grid Columns",
        description="Number of electrode columns in the array.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    electrode_pitch: Annotated[float, Field(gt=0.0)] | list[Annotated[float, Field(gt=0.0)]] = (
        Field(
            default=400.0,
            title="Electrode Pitch",
            description="Centre-to-centre spacing between neighbouring electrodes in micrometers.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            },
        )
    )
    shank_length: Annotated[float, Field(ge=0.0)] | list[Annotated[float, Field(ge=0.0)]] = Field(
        default=1500.0,
        title="Shank Length",
        description=(
            "Length of the electrode shanks in micrometers; the recording tips sit this far along "
            "the insertion direction from the origin."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def get_local_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return the Utah-array tip grid in the local frame.

        The tips form a ``grid_rows`` by ``grid_columns`` grid on an ``electrode_pitch`` spacing in
        the local X-Z plane, centred on the local ``+Y`` axis and offset to ``+Y = shank_length``
        (the shank tips).
        """
        grid_rows = int(self.grid_rows)  # ty:ignore[invalid-argument-type]
        grid_columns = int(self.grid_columns)  # ty:ignore[invalid-argument-type]
        electrode_pitch = float(self.electrode_pitch)  # ty:ignore[invalid-argument-type]
        shank_length = float(self.shank_length)  # ty:ignore[invalid-argument-type]

        # Centre the grid on the local +Y axis.
        row_centre = (grid_rows - 1) / 2.0
        column_centre = (grid_columns - 1) / 2.0
        return [
            (
                (column - column_centre) * electrode_pitch,
                shank_length,
                (row - row_centre) * electrode_pitch,
            )
            for row in range(grid_rows)
            for column in range(grid_columns)
        ]

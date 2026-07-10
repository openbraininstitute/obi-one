from abc import ABC
from typing import Annotated, ClassVar

import numpy as np
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units


def _rotation_matrix(x_deg: float, y_deg: float, z_deg: float) -> np.ndarray:
    """Return the rotation matrix ``Rz(z) @ Rx(x) @ Ry(y)`` (degrees).

    ``Ry`` (roll about the local ``+Y`` axis) is applied first, then ``Rx`` and ``Rz`` aim ``+Y``.
    """
    x, y, z = np.radians([x_deg, y_deg, z_deg])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, np.cos(x), -np.sin(x)], [0.0, np.sin(x), np.cos(x)]])
    ry = np.array([[np.cos(y), 0.0, np.sin(y)], [0.0, 1.0, 0.0], [-np.sin(y), 0.0, np.cos(y)]])
    rz = np.array([[np.cos(z), -np.sin(z), 0.0], [np.sin(z), np.cos(z), 0.0], [0.0, 0.0, 1.0]])
    return rz @ rx @ ry


class ExtracellularLocations(Block):
    """Base class of extracellular locations."""


class XYZExtracellularLocations(ExtracellularLocations):
    """Extracellular locations given as an explicit list of world-coordinate positions."""

    title: ClassVar[str] = "Custom Positions"
    description: ClassVar[str] = "An explicit list of electrode positions in world coordinates."

    xyz_locations: (
        tuple[tuple[float, float, float], ...] | list[tuple[tuple[float, float, float], ...]]
    ) = ((0.0, 0.0, 0.0),)


class PatternedExtracellularLocations(ExtracellularLocations, ABC):
    """Base class for patterned extracellular locations.

    Subclasses define the pattern in a *local* frame via
    :meth:`get_local_electrode_xyz_locations` (origin at ``(0, 0, 0)``, the array running along the
    local ``+Y`` axis). :meth:`get_global_electrode_xyz_locations` places it into world space:
    ``rotation_x`` and ``rotation_z`` aim the local ``+Y`` axis (a 1-D line needs only these) and
    ``origin`` translates it. Planar subclasses add ``rotation_y`` to roll about that axis.
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

    rotation_x: (
        Annotated[float, Field(ge=0.0, lt=360.0)] | list[Annotated[float, Field(ge=0.0, lt=360.0)]]
    ) = Field(
        default=0.0,
        title="Rotation X",
        description="Rotation of the array about the world X axis, in degrees.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )
    rotation_z: (
        Annotated[float, Field(ge=0.0, lt=360.0)] | list[Annotated[float, Field(ge=0.0, lt=360.0)]]
    ) = Field(
        default=0.0,
        title="Rotation Z",
        description="Rotation of the array about the world Z axis, in degrees.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )

    def _roll_degrees(self) -> float:  # noqa: PLR6301
        """Roll about the local ``+Y`` axis, in degrees; 0 for arrays with no lateral extent."""
        return 0.0

    def get_local_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return the electrode locations in the array's local frame.

        The local frame has its origin at ``(0, 0, 0)`` with the array running along the ``+Y``
        axis; ``origin`` and the rotations are *not* applied here (see
        :meth:`get_global_electrode_xyz_locations`).
        """
        msg = "Subclasses must implement get_local_electrode_xyz_locations()."
        raise NotImplementedError(msg)

    def get_global_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return the electrode locations in world coordinates.

        The local pattern from :meth:`get_local_electrode_xyz_locations` is rotated and translated
        by ``origin``: ``rotation_x``/``rotation_z`` aim the local ``+Y`` axis and planar arrays
        roll about it by ``rotation_y``. With all rotations ``0`` this is a pure translation.
        """
        # These methods are only meaningful on single (expanded) configs, where every parameter
        # is a scalar rather than a parameter-sweep list.
        origin = np.array(
            [
                float(self.origin_x),  # ty:ignore[invalid-argument-type]
                float(self.origin_y),  # ty:ignore[invalid-argument-type]
                float(self.origin_z),  # ty:ignore[invalid-argument-type]
            ]
        )
        rotation = _rotation_matrix(
            float(self.rotation_x),  # ty:ignore[invalid-argument-type]
            self._roll_degrees(),
            float(self.rotation_z),  # ty:ignore[invalid-argument-type]
        )
        local = np.asarray(self.get_local_electrode_xyz_locations(), dtype=float)
        world = local @ rotation.T + origin
        return [tuple(position) for position in world.tolist()]


class LinearExtracellularLocations(PatternedExtracellularLocations):
    """Extracellular locations arranged in a linear pattern."""

    title: ClassVar[str] = "Linear Probe"
    description: ClassVar[str] = "A single line of evenly spaced electrodes along the probe axis."

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


class TwoDPatternedExtracellularLocations(PatternedExtracellularLocations, ABC):
    """Base class for planar (2D) patterned extracellular locations.

    Subclasses define the pattern in the local X-Y plane via
    :meth:`get_local_electrode_xy_locations`; this base places it at ``Z = 0``. Unlike the 1-D
    linear array, planar arrays have a lateral extent, so they expose ``rotation_y`` to roll about
    the local ``+Y`` axis.
    """

    rotation_y: (
        Annotated[float, Field(ge=0.0, lt=360.0)] | list[Annotated[float, Field(ge=0.0, lt=360.0)]]
    ) = Field(
        default=0.0,
        title="Rotation Y",
        description="Roll of the array about its long (local +Y) axis, in degrees.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )

    def _roll_degrees(self) -> float:
        return float(self.rotation_y)  # ty:ignore[invalid-argument-type]

    def get_local_electrode_xy_locations(self) -> list[tuple[float, float]]:
        """Return the electrode pattern in the local X-Y plane.

        Subclasses implement this; the base places it at ``Z = 0`` in the local frame.
        """
        msg = "Subclasses must implement get_local_electrode_xy_locations()."
        raise NotImplementedError(msg)

    def get_local_electrode_xyz_locations(self) -> list[tuple[float, float, float]]:
        """Return the planar pattern in the local frame (``Z = 0``)."""
        return [(x, y, 0.0) for x, y in self.get_local_electrode_xy_locations()]


class Neuropixels1ExtracellularLocations(TwoDPatternedExtracellularLocations):
    """Extracellular locations for Neuropixels 1.0 probe."""

    title: ClassVar[str] = "Neuropixels 1.0"
    description: ClassVar[str] = (
        "A Neuropixels 1.0 probe with the imec staggered electrode layout (four columns)."
    )

    n_electrodes: Annotated[int, Field(ge=1)] | list[Annotated[int, Field(ge=1)]] = Field(
        default=384,
        title="Number of Electrodes",
        description="Number of electrodes in the Neuropixels 1.0 probe.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def get_local_electrode_xy_locations(self) -> list[tuple[float, float]]:
        """Return Neuropixels 1.0 electrodes in the local X-Y plane (staggered layout).

        Matches the imec Neuropixels 1.0 geometry: two sites per row 32 um apart, rows 20 um apart,
        with alternate rows offset by a 16 um stagger (four columns at a 16 um pitch). The pattern
        is centred on the local ``+Y`` (long) axis so ``origin`` is the centre of the top of the
        shank.
        """
        row_pitch = 20.0  # vertical spacing between rows (electrode_pitch_vert_um)
        within_row_spacing = 32.0  # horizontal spacing between the two sites in a row (horz pitch)
        row_stagger = 16.0  # horizontal offset applied to alternate rows
        # X of the shank-width centre, so `origin` sits at the centre rather than an edge.
        horizontal_centre = (within_row_spacing + row_stagger) / 2.0

        n_electrodes = int(self.n_electrodes)  # ty:ignore[invalid-argument-type]

        xy_locations = []
        for electrode_i in range(n_electrodes):
            row = electrode_i // 2  # two sites share each row
            column = electrode_i % 2  # 0 or 1 within the row
            # Centre the staggered width on the local +Y axis so the origin is at the centre-top.
            x = column * within_row_spacing + (row % 2) * row_stagger - horizontal_centre
            y = row * row_pitch
            xy_locations.append((x, y))

        return xy_locations


class GridExtracellularLocations(TwoDPatternedExtracellularLocations):
    """Extracellular locations arranged in a rectangular grid of electrodes.

    The electrodes form a ``grid_rows`` by ``grid_columns`` grid in the local X-Y plane, centred on
    the local origin, with ``x_offset`` spacing between columns (along local X) and ``y_offset``
    spacing between rows (along local Y). ``origin`` positions the grid centre and the rotations
    orient it.
    """

    title: ClassVar[str] = "Rectangular Grid"
    description: ClassVar[str] = (
        "A configurable rectangular grid of electrodes with independent row and column spacing."
    )

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
    x_offset: Annotated[float, Field(gt=0.0)] | list[Annotated[float, Field(gt=0.0)]] = Field(
        default=400.0,
        title="X Offset",
        description="Spacing between columns along the local X axis, in micrometers.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    y_offset: Annotated[float, Field(gt=0.0)] | list[Annotated[float, Field(gt=0.0)]] = Field(
        default=400.0,
        title="Y Offset",
        description="Spacing between rows along the local Y axis, in micrometers.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def get_local_electrode_xy_locations(self) -> list[tuple[float, float]]:
        """Return the grid electrodes in the local X-Y plane.

        Electrodes are centred on the origin, spaced ``x_offset`` between columns (X) and
        ``y_offset`` between rows (Y).
        """
        grid_rows = int(self.grid_rows)  # ty:ignore[invalid-argument-type]
        grid_columns = int(self.grid_columns)  # ty:ignore[invalid-argument-type]
        x_offset = float(self.x_offset)  # ty:ignore[invalid-argument-type]
        y_offset = float(self.y_offset)  # ty:ignore[invalid-argument-type]

        row_centre = (grid_rows - 1) / 2.0
        column_centre = (grid_columns - 1) / 2.0
        return [
            ((column - column_centre) * x_offset, (row - row_centre) * y_offset)
            for row in range(grid_rows)
            for column in range(grid_columns)
        ]


class UTAHArrayExtracellularLocations(TwoDPatternedExtracellularLocations):
    """Blackrock Utah array: a fixed 10x10 grid of electrodes at 400 um spacing.

    The grid dimensions and spacing are fixed (unlike :class:`GridExtracellularLocations`); only the
    placement (``origin`` and the rotations) is configurable.
    """

    title: ClassVar[str] = "Utah Array"
    description: ClassVar[str] = (
        "The Blackrock Utah array: a fixed 10x10 grid of electrodes at 400 um spacing."
    )

    GRID_ROWS: ClassVar[int] = 10
    GRID_COLUMNS: ClassVar[int] = 10
    ELECTRODE_SPACING: ClassVar[float] = 400.0

    def get_local_electrode_xy_locations(self) -> list[tuple[float, float]]:
        """Return the fixed 10x10 Utah-array grid (400 um spacing) in the local X-Y plane."""
        row_centre = (self.GRID_ROWS - 1) / 2.0
        column_centre = (self.GRID_COLUMNS - 1) / 2.0
        return [
            (
                (column - column_centre) * self.ELECTRODE_SPACING,
                (row - row_centre) * self.ELECTRODE_SPACING,
            )
            for row in range(self.GRID_ROWS)
            for column in range(self.GRID_COLUMNS)
        ]

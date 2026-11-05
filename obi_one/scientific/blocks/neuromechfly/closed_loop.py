"""Blocks of a NeuroMechFly closed-loop experiment: the body's world, and what is done to it.

Which neurons the body drives and reads, and how, is the circuit's body interface
(``obi_one.scientific.library.simulation.neuromechfly.interface``), not the simulation's. These
blocks make the rest of the simulation config's ``neuromechfly`` section.
"""

from typing import ClassVar, Literal

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.library.simulation.neuromechfly.config import (
    ArenaConfig,
    BodySegment,
    ForceConfig,
    Leg,
    LegJoint,
    LegMode,
    LegOverrideConfig,
)
from obi_one.scientific.library.simulation.neuromechfly.interface import OdourClass

ODOUR_TITLES = {
    "yeasty_volatile": "Yeasty",
    "fruity_volatile": "Fruity",
    "alcoholic_fermentation_volatile": "Alcoholic fermentation",
    "decaying_fruit_volatile": "Decaying fruit",
    "plant_matter_volatile": "Plant matter",
    "animal_matter_volatile": "Animal matter",
    "carbon_dioxide_volatile": "Carbon dioxide",
    "aversive_volatile": "Aversive",
    "pheromone_volatile": "Pheromone",
}


def position_field(title: str, description: str, default: float = 0.0) -> float | list[float]:
    """A coordinate on the arena floor, in mm."""
    return Field(
        default=default,
        title=title,
        description=description,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIMETERS,
        },
    )


def episode_time_field(title: str, description: str, default: float) -> float | list[float]:
    """A time on the body's clock, in ms from when the episode starts."""
    return Field(
        default=default,
        title=title,
        description=description,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )


def force_field(title: str, description: str, default: float = 0.0) -> float | list[float]:
    """One component of a force, in μN."""
    return Field(
        default=default,
        title=title,
        description=description,
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MICRONEWTONS,
        },
    )


class OdourSource(Block):
    """A source of odour on the arena floor.

    Its odour drives the circuit's olfactory receptor neurons of the same class, each by the
    intensity at its own antenna or palp; the circuit does the rest.
    """

    title: ClassVar[str] = "Odour source"

    odour: OdourClass = Field(
        default="yeasty_volatile",
        title="Odour",
        description="Which receptor neurons the odour drives: those of its class.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
            SchemaKey.TITLE_BY_KEY: {**ODOUR_TITLES},
            SchemaKey.DESCRIPTION_BY_KEY: {
                key: f"Drives the receptor neurons classed {title.lower()} (BANC's "
                "cell_function_detailed)."
                for key, title in ODOUR_TITLES.items()
            },
        },
    )

    x: float | list[float] = position_field(
        "X", "X (mm) on the arena floor. The fly starts at the origin, facing +X.", default=25.0
    )
    y: float | list[float] = position_field(
        "Y", "Y (mm) on the arena floor: +Y is to the fly's left at a start heading of 0."
    )


class Wall(Block):
    """A wall from (x0, y0) to (x1, y1), 1.2 mm thick and 3 mm high.

    The fly cannot see walls yet (vision is not simulated): it only bumps into them.
    """

    title: ClassVar[str] = "Wall"

    x0: float | list[float] = position_field("Start X", "X (mm) of one end.", default=15.0)
    y0: float | list[float] = position_field("Start Y", "Y (mm) of one end.", default=-4.0)
    x1: float | list[float] = position_field("End X", "X (mm) of the other end.", default=15.0)
    y1: float | list[float] = position_field("End Y", "Y (mm) of the other end.", default=6.0)


class OdourArena(Block):
    """The flat arena the fly walks in, starting at the origin."""

    title: ClassVar[str] = "Arena"

    peak_odour_intensity: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Peak odour intensity",
        description="Intensity of each source; it falls with the inverse square of distance.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    capture_radius: PositiveFloat | list[PositiveFloat] = Field(
        default=2.5,
        title="Capture radius",
        description="Distance from a source at which the fly reaches it.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLIMETERS,
        },
    )
    start_heading: float | list[float] = Field(
        default=0.0,
        title="Start heading",
        description="Direction the fly faces at the start, anticlockwise from +X.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )

    def section(self, sources: list[OdourSource], walls: list[Wall]) -> ArenaConfig:
        """The arena part of the ``neuromechfly`` section, with its sources and walls."""
        return ArenaConfig(
            odour_sources=tuple((source.x, source.y) for source in sources),  # ty:ignore[invalid-argument-type]
            odour_classes=tuple(source.odour for source in sources),
            walls=tuple((wall.x0, wall.y0, wall.x1, wall.y1) for wall in walls),  # ty:ignore[invalid-argument-type]
            peak_odour_intensity=self.peak_odour_intensity,  # ty:ignore[invalid-argument-type]
            capture_radius=self.capture_radius,  # ty:ignore[invalid-argument-type]
            start_heading=self.start_heading,  # ty:ignore[invalid-argument-type]
        )


class BodyForce(Block):
    """A push on one part of the body, for a window of the episode.

    The fly weighs about 10 μN: a push of a few μN shifts it, and twice its weight sideways sends
    it sliding across the floor.
    """

    title: ClassVar[str] = "Body force"

    segment: BodySegment = Field(
        default="thorax",
        title="Body part",
        description="Where the force acts, at that part's centre of mass.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
            SchemaKey.TITLE_BY_KEY: {
                "thorax": "Thorax",
                "head": "Head",
                "abdomen": "Abdomen",
                "left_front_leg": "Left front leg",
                "left_middle_leg": "Left middle leg",
                "left_hind_leg": "Left hind leg",
                "right_front_leg": "Right front leg",
                "right_middle_leg": "Right middle leg",
                "right_hind_leg": "Right hind leg",
            },
            SchemaKey.DESCRIPTION_BY_KEY: {
                "thorax": "The middle of the body, where the legs and wings attach.",
                "head": "The head.",
                "abdomen": "The abdomen. The trunk is rigid, so this pushes the whole body.",
                "left_front_leg": "The left front leg, at its tibia.",
                "left_middle_leg": "The left middle leg, at its tibia.",
                "left_hind_leg": "The left hind leg, at its tibia.",
                "right_front_leg": "The right front leg, at its tibia.",
                "right_middle_leg": "The right middle leg, at its tibia.",
                "right_hind_leg": "The right hind leg, at its tibia.",
            },
        },
    )
    frame: Literal["body", "arena"] = Field(
        default="body",
        title="Direction frame",
        description="What the force's axes are measured against.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
            SchemaKey.TITLE_BY_KEY: {"body": "The fly", "arena": "The arena"},
            SchemaKey.DESCRIPTION_BY_KEY: {
                "body": "X forward, Y to the fly's left, Z up, turning with the fly.",
                "arena": "The arena's X, Y and Z, whichever way the fly faces.",
            },
        },
    )
    force_x: float | list[float] = force_field("Force along X", "Forward, or the arena's X.")
    force_y: float | list[float] = force_field(
        "Force along Y", "To the fly's left, or the arena's Y.", default=2.0
    )
    force_z: float | list[float] = force_field("Force along Z", "Up.")
    start: NonNegativeFloat | list[NonNegativeFloat] = episode_time_field(
        "Start", "When the force begins, after the episode starts.", 1000.0
    )
    duration: PositiveFloat | list[PositiveFloat] = episode_time_field(
        "Duration", "How long the force lasts.", 200.0
    )
    frequency: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=0.0,
        title="Frequency",
        description="0 holds the force steady; above 0 it oscillates as a sine.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    def config(self) -> ForceConfig:
        """The force as the closed loop takes it."""
        return ForceConfig(
            segment=self.segment,
            force=(self.force_x, self.force_y, self.force_z),  # ty:ignore[invalid-argument-type]
            frame=self.frame,
            start=self.start,  # ty:ignore[invalid-argument-type]
            duration=self.duration,  # ty:ignore[invalid-argument-type]
            frequency=self.frequency,  # ty:ignore[invalid-argument-type]
        )


class LegOverride(Block):
    """One leg taken from its muscles for a window of the episode, as if held by hand.

    The circuit's motor neurons keep driving the other legs.
    """

    title: ClassVar[str] = "Leg override"

    leg: Leg = Field(
        default="left_front",
        title="Leg",
        description="Which leg.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
            SchemaKey.TITLE_BY_KEY: {
                "left_front": "Left front",
                "left_middle": "Left middle",
                "left_hind": "Left hind",
                "right_front": "Right front",
                "right_middle": "Right middle",
                "right_hind": "Right hind",
            },
            SchemaKey.DESCRIPTION_BY_KEY: {
                "left_front": "The left foreleg.",
                "left_middle": "The left middle leg.",
                "left_hind": "The left hind leg.",
                "right_front": "The right foreleg.",
                "right_middle": "The right middle leg.",
                "right_hind": "The right hind leg.",
            },
        },
    )
    mode: LegMode = Field(
        default="lift",
        title="Mode",
        description="What happens to the leg.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
            SchemaKey.TITLE_BY_KEY: {
                "hold": "Hold",
                "lift": "Lift",
                "limp": "Limp",
                "swing": "Swing",
            },
            SchemaKey.DESCRIPTION_BY_KEY: {
                "hold": "Frozen as it is when the window opens; a planted foot keeps its grip.",
                "lift": "Raised clear of the floor and held there.",
                "limp": "Muscles cut: only its joints' passive springs hold the leg.",
                "swing": "Held, with one joint swung back and forth as a sine.",
            },
        },
    )
    start: NonNegativeFloat | list[NonNegativeFloat] = episode_time_field(
        "Start", "When the leg is taken, after the episode starts.", 1000.0
    )
    duration: PositiveFloat | list[PositiveFloat] = episode_time_field(
        "Duration", "How long the leg is held.", 500.0
    )
    joint: LegJoint = Field(
        default="tibia",
        title="Swung joint",
        description="The joint a swing moves.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
            SchemaKey.TITLE_BY_KEY: {
                "coxa": "Coxa (pitch)",
                "coxa_roll": "Coxa (roll)",
                "coxa_yaw": "Coxa (yaw)",
                "femur": "Femur (pitch)",
                "femur_roll": "Femur (roll)",
                "tibia": "Tibia",
                "tarsus": "Tarsus",
            },
            SchemaKey.DESCRIPTION_BY_KEY: {
                "coxa": "Body-coxa joint, swinging the leg forward and back.",
                "coxa_roll": "Body-coxa joint, rolling the leg.",
                "coxa_yaw": "Body-coxa joint, turning the leg about its length.",
                "femur": "Coxa-trochanter joint, raising and lowering the femur.",
                "femur_roll": "Trochanter-femur joint, rolling the femur.",
                "tibia": "Femur-tibia joint (the knee).",
                "tarsus": "Tibia-tarsus joint (the ankle).",
            },
        },
    )
    amplitude: float | list[float] = Field(
        default=20.0,
        title="Swing amplitude",
        description="How far a swing moves the joint either way.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )
    frequency: PositiveFloat | list[PositiveFloat] = Field(
        default=5.0,
        title="Swing frequency",
        description="How fast a swing goes back and forth.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    def config(self) -> LegOverrideConfig:
        """The override as the closed loop takes it."""
        return LegOverrideConfig(
            leg=self.leg,
            mode=self.mode,
            start=self.start,  # ty:ignore[invalid-argument-type]
            duration=self.duration,  # ty:ignore[invalid-argument-type]
            joint=self.joint,
            amplitude=self.amplitude,  # ty:ignore[invalid-argument-type]
            frequency=self.frequency,  # ty:ignore[invalid-argument-type]
        )

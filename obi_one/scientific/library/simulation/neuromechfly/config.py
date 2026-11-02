"""The ``neuromechfly`` section of a Brian2 SONATA simulation config: the experiment.

Which neurons the body drives and reads, and how, belong to the circuit (``interface.py``). The
simulation says what world the body is in, and what is manipulated: forces on the body and legs
taken over, timed on the body's clock, which starts with the network's.
"""

import math
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    model_validator,
)

from obi_one.scientific.library.simulation.neuromechfly.interface import OdourClass

SECTION = "neuromechfly"

BodySegment = Literal[
    "thorax",
    "head",
    "abdomen",
    "left_front_leg",
    "left_middle_leg",
    "left_hind_leg",
    "right_front_leg",
    "right_middle_leg",
    "right_hind_leg",
]
Leg = Literal["left_front", "left_middle", "left_hind", "right_front", "right_middle", "right_hind"]
LegJoint = Literal["coxa", "coxa_roll", "coxa_yaw", "femur", "femur_roll", "tibia", "tarsus"]
LegMode = Literal["hold", "lift", "limp", "swing"]


class ArenaConfig(BaseModel):
    """A flat arena with odour sources and walls, in mm; the fly starts at the origin."""

    model_config = ConfigDict(extra="forbid")

    odour_sources: tuple[tuple[float, float], ...] = Field(min_length=1)
    odour_classes: tuple[OdourClass, ...] = Field(
        default=(),
        description="Each source's odour, as the circuit's receptor neurons are classed; "
        "yeasty_volatile for every source if empty.",
    )
    source_height: NonNegativeFloat = 1.5
    peak_odour_intensity: PositiveFloat = 1.0
    walls: tuple[tuple[float, float, float, float], ...] = ()
    wall_thickness: PositiveFloat = 1.2
    wall_height: PositiveFloat = 3.0
    capture_radius: PositiveFloat = 2.5
    start_heading: float = Field(default=0.0, description="Degrees, anticlockwise from +x.")

    @model_validator(mode="after")
    def check_odour_classes(self) -> Self:
        """One odour class per source."""
        if not self.odour_classes:
            self.odour_classes = ("yeasty_volatile",) * len(self.odour_sources)
        if len(self.odour_classes) != len(self.odour_sources):
            msg = "odour_classes needs one class per odour source."
            raise ValueError(msg)
        return self


class Perturbation(BaseModel):
    """A window of the episode, on the body's clock: ms from the start of the simulation."""

    model_config = ConfigDict(extra="forbid")

    start: NonNegativeFloat = Field(description="ms after the episode starts")
    duration: PositiveFloat = Field(description="ms")

    def active(self, time_ms: float) -> bool:
        """Whether the window is open at ``time_ms`` of body time."""
        return self.start <= time_ms < self.start + self.duration


class ForceConfig(Perturbation):
    """A push on one body segment, in μN (the fly weighs about 10 μN).

    In the ``body`` frame the force's axes are the fly's forward, left and up, turning with its
    heading but not its pitch or roll; in the ``arena`` frame they are the arena's x, y and z.
    """

    segment: BodySegment
    force: tuple[float, float, float] = Field(description="μN")
    frame: Literal["body", "arena"] = "body"
    frequency: NonNegativeFloat = Field(
        default=0.0, description="Hz: 0 holds the force steady, above 0 it is a sine."
    )

    def scale_at(self, time_ms: float) -> float:
        """The share of ``force`` applied at ``time_ms``: 0 outside the window."""
        if not self.active(time_ms):
            return 0.0
        if self.frequency == 0:
            return 1.0
        return math.sin(2 * math.pi * self.frequency * (time_ms - self.start) / 1000)


class LegOverrideConfig(Perturbation):
    """One leg taken from its muscles for a window of the episode, as if held by hand.

    ``hold`` freezes the leg as it is when the window opens, ``lift`` raises it clear of the floor,
    ``limp`` cuts its muscles' torques, leaving only the joints' passive properties, and ``swing``
    holds it but swings ``joint`` as a sine. A held leg keeps its grip on the ground; a lifted, limp
    or swinging one lets go.
    """

    leg: Leg
    mode: LegMode
    joint: LegJoint = "tibia"
    amplitude: float = Field(default=20.0, description="degrees (swing)")
    frequency: PositiveFloat = Field(default=5.0, description="Hz (swing)")


class ClosedLoopConfig(BaseModel):
    """The closed loop: the body and the network run together from the start, exchanging every
    ``coupling_step``: the motor neurons' muscles move the body, and the body's senses set the
    firing of the sensory neurons.
    """

    model_config = ConfigDict(extra="forbid")

    coupling_step: PositiveFloat = Field(default=1.0, description="ms")
    body_timestep: PositiveFloat = Field(default=0.1, description="ms")
    arena: ArenaConfig
    forces: tuple[ForceConfig, ...] = ()
    leg_overrides: tuple[LegOverrideConfig, ...] = Field(
        default=(), description="Where two take the same leg at once, the later one wins."
    )

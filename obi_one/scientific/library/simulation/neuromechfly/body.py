"""The NeuroMechFly body (flygym 1.2) in an odour arena, moved only by torques on its leg joints.

The torques come from the circuit's muscles (``wiring.Muscles``); besides them, each actuated joint
has a passive stiffness towards the standing pose and a damping, as the circuit's body interface
sets them. An experiment can push the body and take legs over for a while (see
``config.ForceConfig`` and ``config.LegOverrideConfig``). The body records its state as it goes,
for replaying the episode in 3D (``Body.frames``).

Needs flygym, which is not an obi-one dependency: the closed-loop launch job installs it.
"""

import math
import sys
import types
from dataclasses import dataclass

import numpy as np

try:
    import cv2  # ruff: ignore[unused-import]  # ty:ignore[unresolved-import]
except ImportError:
    # flygym imports OpenCV for its cameras, which the closed loop has none of, and the launch
    # image (python:3.12-slim) lacks the X libraries opencv-python loads: a stand-in will do.
    sys.modules["cv2"] = types.ModuleType("cv2")

from flygym import Fly, PhysicsError, SingleFlySimulation  # ty:ignore[unresolved-import]
from flygym.arena import OdorArena  # ty:ignore[unresolved-import]
from flygym.examples.locomotion import PreprogrammedSteps  # ty:ignore[unresolved-import]
from flygym.state import KinematicPose  # ty:ignore[unresolved-import]

from obi_one.scientific.library.simulation.neuromechfly.config import (
    ArenaConfig,
    ForceConfig,
    LegOverrideConfig,
)
from obi_one.scientific.library.simulation.neuromechfly.interface import JOINTS, LEGS, Motor

# The config's names for the legs, in LEGS order, and for their joints, in JOINTS order.
LEG_NAMES = ("left_front", "left_middle", "left_hind", "right_front", "right_middle", "right_hind")
LEG_JOINTS = ("coxa", "coxa_roll", "coxa_yaw", "femur", "femur_roll", "tibia", "tarsus")
# Raising the femur this far (radians, 69 degrees) from the standing pose holds a foot about 1 mm
# off the floor. A negative femur angle raises the leg.
LIFT_FEMUR_RADIANS = -1.2
# A leg an override takes follows its targets through these gains, as flygym's position actuators
# would: the experimenter's hand, not the circuit's muscles. The hand also cancels the joints'
# passive springs, so the leg goes where it is put.
OVERRIDE_STIFFNESS = 45.0  # μN·mm/radian
OVERRIDE_DAMPING = 0.5  # μN·mm·s/radian
# The flygym body a force on each segment acts on (at its centre of mass). The trunk is rigid, so
# the abdomen's middle segment carries a push on the abdomen to the whole body.
SEGMENT_BODIES = {
    "thorax": "Thorax",
    "head": "Head",
    "abdomen": "A3",
    **{f"{name}_leg": f"{leg}Tibia" for name, leg in zip(LEG_NAMES, LEGS, strict=True)},
}
LEG_SEGMENTS = ("Tibia", "Tarsus1", "Tarsus2", "Tarsus3", "Tarsus4", "Tarsus5")
CONTACT_SENSORS = [f"{leg}{segment}" for leg in LEGS for segment in LEG_SEGMENTS]
SPAWN_HEIGHT_MM = 0.2
# The bodies of a leg's chain, from the coxa out. A replay frame holds every joint of each, in the
# model's order, as minnick2026/viewer/export_kinematics.py exports them for the viewer.
LEG_CHAIN = ("Coxa", "Femur", "Tibia", "Tarsus1", "Tarsus2", "Tarsus3", "Tarsus4", "Tarsus5")


class OdourArenaWithWalls(OdorArena):
    """flygym's odour arena, with box walls and one odour dimension per odour class."""

    def __init__(self, arena: ArenaConfig) -> None:
        """Place the sources at ``source_height``, each emitting its class, and the walls."""
        #: The odour classes in the arena, in the order of flygym's odour dimensions.
        self.classes = tuple(sorted(set(arena.odour_classes)))
        sources = np.array([(x, y, arena.source_height) for x, y in arena.odour_sources])
        peaks = np.zeros((len(sources), len(self.classes)))
        for source, odour in enumerate(arena.odour_classes):
            peaks[source, self.classes.index(odour)] = arena.peak_odour_intensity
        super().__init__(
            odor_source=sources,
            peak_odor_intensity=peaks,
            diffuse_func=lambda distance: distance**-2,
        )
        for index, (x0, y0, x1, y1) in enumerate(arena.walls):
            self.root_element.worldbody.add(
                "geom",
                name=f"wall_{index}",
                type="box",
                size=(
                    math.hypot(x1 - x0, y1 - y0) / 2,
                    arena.wall_thickness / 2,
                    arena.wall_height / 2,
                ),
                pos=((x0 + x1) / 2, (y0 + y1) / 2, arena.wall_height / 2),
                euler=(0, 0, math.atan2(y1 - y0, x1 - x0)),
                rgba=(0.4, 0.4, 0.4, 1),
            )


@dataclass(frozen=True)
class BodyState:
    """What the body's senses read: joints by leg (LEGS) and joint (JOINTS), in radians."""

    angles: np.ndarray
    velocities: np.ndarray
    accelerations: np.ndarray
    #: The standing pose, which the hair plates measure deflection from.
    rest: np.ndarray
    #: Each leg's contact forces, summed (μN), and their rate of change (μN/s).
    load: np.ndarray
    load_change: np.ndarray
    #: The odour classes in the arena and their intensity at the left palp, right palp, left
    #: antenna and right antenna, one row per class.
    odour_classes: tuple[str, ...]
    odour: np.ndarray


class LegOverride:
    """What one leg is held to while its override's window is open.

    The posture to hold is read when the window opens. A limp leg gets no torque at all, leaving
    its joints to their passive springs.
    """

    def __init__(
        self, config: LegOverrideConfig, rest: np.ndarray, passive_stiffness: float
    ) -> None:
        """Take ``config``'s leg; ``rest`` is its standing pose (seven joints)."""
        self.config = config
        self.leg = LEG_NAMES.index(config.leg)
        self.rest = rest
        self.passive_stiffness = passive_stiffness
        self.posture: np.ndarray | None = None

    def torques(
        self, time_ms: float, angles: np.ndarray, velocities: np.ndarray
    ) -> tuple[np.ndarray, float] | None:
        """The leg's joint torques and adhesion at ``time_ms``; None while the window is shut.

        ``angles`` and ``velocities`` are the leg's seven joints now.
        """
        if not self.config.active(time_ms):
            self.posture = None
            return None
        if self.config.mode == "limp":
            return np.zeros(len(LEG_JOINTS)), 0.0
        if self.posture is None:
            self.posture = angles.copy()
            if self.config.mode == "lift":
                self.posture = self.rest.copy()
                self.posture[LEG_JOINTS.index("femur")] += LIFT_FEMUR_RADIANS
        target = self.posture.copy()
        if self.config.mode == "swing":
            phase = 2 * math.pi * self.config.frequency * (time_ms - self.config.start) / 1000
            target[LEG_JOINTS.index(self.config.joint)] += math.radians(
                self.config.amplitude
            ) * math.sin(phase)
        torques = (
            OVERRIDE_STIFFNESS * (target - angles)
            - OVERRIDE_DAMPING * velocities
            + self.passive_stiffness * (angles - self.rest)
        )
        # A held foot keeps its grip; a lifted or swinging one lets go.
        return torques, 1.0 if self.config.mode == "hold" else 0.0


class Body:
    """The fly in its arena: torques and adhesion in, its state out, sources noted on arrival."""

    def __init__(
        self,
        arena: ArenaConfig,
        *,
        timestep_ms: float,
        seed: int,
        motor: Motor,
        forces: tuple[ForceConfig, ...] = (),
        leg_overrides: tuple[LegOverrideConfig, ...] = (),
        frame_ms: float | None = None,
    ) -> None:
        """Build the arena and the fly, standing, and reset them with ``seed``.

        With ``frame_ms``, the body records a frame (see ``frame``) when it starts and every
        ``frame_ms`` of body time after, rounded to whole physics steps.
        """
        self.config = arena
        self.arena = OdourArenaWithWalls(arena)
        steps = PreprogrammedSteps()
        #: The standing pose (LEGS by JOINTS), which the joints' passive springs pull towards.
        self.rest = np.array([np.ravel(steps.neutral_pos[leg]) for leg in LEGS])
        names = [f"joint_{leg}{joint}" for leg in LEGS for joint in JOINTS]
        fly = Fly(
            enable_adhesion=True,
            draw_adhesion=False,
            enable_olfaction=True,
            enable_vision=False,
            contact_sensor_placements=CONTACT_SENSORS,
            spawn_pos=(0.0, 0.0, SPAWN_HEIGHT_MM),
            spawn_orientation=(0.0, 0.0, math.radians(arena.start_heading)),
            control="motor",
            actuator_gain=None,
            actuator_forcerange=motor.joint_torque_limit,
            joint_stiffness=motor.passive_stiffness,
            joint_damping=motor.passive_damping,
            init_pose=KinematicPose(dict(zip(names, self.rest.ravel(), strict=True))),
        )
        for name, angle in zip(names, self.rest.ravel(), strict=True):
            fly.model.find("joint", name).springref = angle
        self.sim = SingleFlySimulation(
            fly=fly, arena=self.arena, cameras=[], timestep=timestep_ms / 1000
        )
        self.obs, _ = self.sim.reset(seed=seed)
        self.physics_fault = False
        self.timestep_ms = timestep_ms
        self.physics_steps = 0
        physics = self.sim.physics
        self.forces = [
            (force, physics.model.name2id(f"{fly.name}/{SEGMENT_BODIES[force.segment]}", "body"))
            for force in forces
        ]
        self.leg_overrides = [
            LegOverride(override, self.rest[LEG_NAMES.index(override.leg)], motor.passive_stiffness)
            for override in leg_overrides
        ]
        model = physics.model
        self.thorax = model.name2id(f"{fly.name}/Thorax", "body")
        self.leg_joints = np.array(
            [
                model.jnt_qposadr[joint]
                for leg in LEGS
                for segment in LEG_CHAIN
                for joint in joints_of(model, model.name2id(f"{fly.name}/{leg}{segment}", "body"))
            ]
        )
        self.previous_velocities = self.joint_velocities
        self.previous_load = self.leg_load
        self.record_every = max(1, round(frame_ms / timestep_ms)) if frame_ms else 0
        self.frames: list[dict] = [self.frame()] if self.record_every else []
        #: Each source reached, with the body time it was first reached at (ms).
        self.reached: list[tuple[int, float]] = []
        self.remaining = np.ones(len(arena.odour_sources), dtype=bool)

    @property
    def time_ms(self) -> float:
        """Body time since the episode started, in ms."""
        return self.physics_steps * self.timestep_ms

    @property
    def joint_angles(self) -> np.ndarray:
        """The actuated joints' angles (LEGS by JOINTS), radians."""
        return np.asarray(self.obs["joints"][0], dtype=float).reshape(len(LEGS), len(JOINTS))

    @property
    def joint_velocities(self) -> np.ndarray:
        """The actuated joints' angular velocities (LEGS by JOINTS), radians/s."""
        return np.asarray(self.obs["joints"][1], dtype=float).reshape(len(LEGS), len(JOINTS))

    @property
    def position(self) -> np.ndarray:
        """Thorax position (x, y, z) in mm."""
        return np.asarray(self.obs["fly"][0], dtype=float)

    @property
    def upright(self) -> bool:
        """Whether the fly is right side up."""
        return float(np.asarray(self.obs["cardinal_vectors"])[2][2]) > 0

    @property
    def heading(self) -> float:
        """Degrees, anticlockwise from +x."""
        orientation = self.obs["fly_orientation"]
        return math.degrees(math.atan2(orientation[1], orientation[0]))

    @property
    def leg_load(self) -> np.ndarray:
        """Each leg's contact forces, summed (μN)."""
        forces = np.linalg.norm(np.asarray(self.obs["contact_forces"], dtype=float), axis=1)
        return forces.reshape(len(LEGS), len(LEG_SEGMENTS)).sum(axis=1)

    def state(self, interval_ms: float) -> BodyState:
        """The body's state now, its rates of change over the last ``interval_ms``."""
        velocities, load = self.joint_velocities, self.leg_load
        seconds = interval_ms / 1000
        accelerations = (velocities - self.previous_velocities) / seconds
        load_change = (load - self.previous_load) / seconds
        self.previous_velocities, self.previous_load = velocities, load
        return BodyState(
            angles=self.joint_angles,
            velocities=velocities,
            accelerations=accelerations,
            rest=self.rest,
            load=load,
            load_change=load_change,
            odour_classes=self.arena.classes,
            odour=np.asarray(self.obs["odor_intensity"], dtype=float),
        )

    def advance(self, torques: np.ndarray, adhesion: np.ndarray, steps: int) -> bool:
        """Step the physics ``steps`` times with the muscles' joint ``torques`` and ``adhesion``.

        ``torques`` holds the actuated joints in LEGS by JOINTS order, ``adhesion`` one value per
        leg in [0, 1]. Returns whether a force or a leg override acted. A physics fault (the body
        falling apart) stops the body; ``physics_fault`` then stays set.
        """
        perturbed = False
        for _ in range(steps):
            joints, grip, acting = self.perturb(torques, adhesion)
            perturbed |= acting
            try:
                self.obs, _, _, _, _ = self.sim.step({"joints": joints, "adhesion": grip})
            except PhysicsError:
                self.physics_fault = True
                return perturbed
            self.physics_steps += 1
            if self.record_every and self.physics_steps % self.record_every == 0:
                self.frames.append(self.frame())
        return perturbed

    def perturb(
        self, torques: np.ndarray, adhesion: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, bool]:
        """Apply this physics step's forces, and replace the torques of the legs taken over.

        Returns the joint torques and adhesion to send, and whether a force or an override acted.
        """
        applied = self.sim.physics.data.xfrc_applied
        for _, body in self.forces:
            applied[body, :3] = 0
        acting = False
        for (_, body), vector in zip(self.forces, self.force_vectors(), strict=True):
            if vector is not None:
                applied[body, :3] += vector
                acting = True
        joints = np.asarray(torques, dtype=float).reshape(len(LEGS), len(JOINTS)).copy()
        grip = np.asarray(adhesion, dtype=float).copy()
        angles, velocities = self.joint_angles, self.joint_velocities
        for override in self.leg_overrides:
            taken = override.torques(self.time_ms, angles[override.leg], velocities[override.leg])
            if taken is not None:
                joints[override.leg], grip[override.leg] = taken
                acting = True
        return joints.ravel(), grip, acting

    def force_vectors(self) -> list[np.ndarray | None]:
        """Each force in the arena's frame (μN) at this step, or None while it is off."""
        heading = math.radians(self.heading)
        # The body frame: forward, left and up, as columns.
        frame = np.array(
            [
                [math.cos(heading), -math.sin(heading), 0.0],
                [math.sin(heading), math.cos(heading), 0.0],
                [0.0, 0.0, 1.0],
            ]
        )
        vectors: list[np.ndarray | None] = []
        for force, _ in self.forces:
            if not force.active(self.time_ms):
                vectors.append(None)
                continue
            vector = np.asarray(force.force) * force.scale_at(self.time_ms)
            vectors.append(frame @ vector if force.frame == "body" else vector)
        return vectors

    def frame(self) -> dict:
        """The body's state now, for a replay.

        The thorax's position (mm) and orientation (w, x, y, z), every joint of every leg's chain
        (radians; legs in LEGS order, joints in ``LEG_CHAIN`` order), each force as where it acts
        (its segment's centre of mass, mm) and how hard (μN), or None while it is off, which leg
        overrides are on, and whether the fly is upright.
        """
        data = self.sim.physics.data
        return {
            "thorax": [*data.xpos[self.thorax], *data.xquat[self.thorax]],
            "joints": data.qpos[self.leg_joints].tolist(),
            "forces": [
                None if vector is None else [*data.xipos[body], *vector]
                for (_, body), vector in zip(self.forces, self.force_vectors(), strict=True)
            ],
            "overrides": [override.config.active(self.time_ms) for override in self.leg_overrides],
            "upright": self.upright,
        }

    def note_sources(self) -> list[int]:
        """Note the sources within the capture radius for the first time; return their indices.

        A source keeps emitting once reached: what the fly does there is up to its circuit.
        """
        sources = np.asarray(self.config.odour_sources)
        near = np.linalg.norm(sources - self.position[:2], axis=1) <= self.config.capture_radius
        reached = np.flatnonzero(near & self.remaining).tolist()
        for source in reached:
            self.remaining[source] = False
            self.reached.append((source, self.time_ms))
        return reached


def joints_of(model: object, body: int) -> range:
    """The ids of body ``body``'s joints, in the model's order."""
    first = int(model.body_jntadr[body])  # ty:ignore[unresolved-attribute]
    return range(first, first + int(model.body_jntnum[body]))  # ty:ignore[unresolved-attribute]

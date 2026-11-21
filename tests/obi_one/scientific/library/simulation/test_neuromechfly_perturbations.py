"""The torque-driven flygym body on its own: muscles' torques, pushes, and legs taken over.

flygym is not an obi-one dependency (the closed-loop launch job installs it), so these tests only
run where it is installed.
"""

import math

import numpy as np
import pytest

pytest.importorskip("flygym")

from obi_one.scientific.library.simulation.neuromechfly.body import LEG_JOINTS, LEGS, Body
from obi_one.scientific.library.simulation.neuromechfly.config import (
    ArenaConfig,
    ForceConfig,
    LegOverrideConfig,
)
from obi_one.scientific.library.simulation.neuromechfly.interface import JOINTS, Motor

ARENA = ArenaConfig(odour_sources=((40.0, 0.0),))
MOTOR = Motor()
PHYSICS_PER_MS = 10


def body(**kwargs) -> Body:
    return Body(ARENA, timestep_ms=0.1, seed=0, motor=MOTOR, **kwargs)


def run(fly: Body, ms: float, torques: np.ndarray | None = None) -> bool:
    """Run ``ms`` of body time with silent muscles or ``torques``; whether anything acted."""
    return fly.advance(
        np.zeros(42) if torques is None else torques, np.zeros(6), round(ms * PHYSICS_PER_MS)
    )


def joint(leg: str, name: str) -> int:
    return LEGS.index(leg) * len(JOINTS) + JOINTS.index(name)


class TestPassiveBody:
    def test_with_silent_muscles_the_fly_stands_on_its_joints_springs(self):
        fly = body()
        run(fly, 300)

        assert fly.upright
        assert fly.position[2] > 0.8
        assert not fly.physics_fault


class TestMuscleTorques:
    def test_a_positive_tibia_torque_flexes_the_knee(self):
        plain, flexed = body(), body()
        torques = np.zeros(42)
        torques[joint("LF", "Tibia")] = 10.0

        run(plain, 100)
        run(flexed, 100, torques)

        tibia = JOINTS.index("Tibia")
        # against the joint's passive spring (20 μN·mm/radian), about half a radian
        assert flexed.joint_angles[0, tibia] > plain.joint_angles[0, tibia] + 0.3

    def test_a_negative_femur_torque_raises_the_leg(self):
        plain, raised = body(), body()
        torques = np.zeros(42)
        torques[joint("RM", "Femur")] = -15.0

        run(plain, 100)
        run(raised, 100, torques)

        foot = LEGS.index("RM")
        assert raised.obs["end_effectors"][foot, 2] > plain.obs["end_effectors"][foot, 2] + 0.1


class TestForces:
    def test_a_push_to_the_left_moves_the_fly_left_while_it_lasts(self):
        plain = body()
        run(plain, 300)
        push = ForceConfig(segment="thorax", force=(0.0, 5.0, 0.0), start=50.0, duration=200.0)
        pushed = body(forces=(push,))

        flags = [run(pushed, 50) for _ in range(6)]

        assert flags == [False, True, True, True, True, False]
        assert pushed.position[1] > plain.position[1] + 0.1
        # the push stops with its window
        assert np.all(pushed.sim.physics.data.xfrc_applied == 0)


class TestLegOverrides:
    def test_a_lifted_leg_leaves_the_floor(self):
        lift = LegOverrideConfig(leg="right_middle", mode="lift", start=0.0, duration=300.0)
        fly = body(leg_overrides=(lift,))

        run(fly, 200)

        assert fly.obs["end_effectors"][LEGS.index("RM"), 2] > 0.5

    def test_a_held_leg_keeps_its_posture(self):
        hold = LegOverrideConfig(leg="left_front", mode="hold", start=50.0, duration=200.0)
        fly = body(leg_overrides=(hold,))
        run(fly, 50.1)
        held = fly.leg_overrides[0].posture.copy()
        torques = np.zeros(42)
        torques[joint("LF", "Tibia")] = 20.0

        run(fly, 100, torques)

        # the muscles pull at the tibia, but the hand holding the leg wins
        np.testing.assert_allclose(fly.joint_angles[0], held, atol=0.15)

    def test_a_swing_moves_one_joint_as_a_sine(self):
        swing = LegOverrideConfig(
            leg="left_hind",
            mode="swing",
            joint="tibia",
            amplitude=20.0,
            frequency=5.0,
            start=0.0,
            duration=500.0,
        )
        fly = body(leg_overrides=(swing,))
        tibia = LEG_JOINTS.index("tibia")
        angles = []
        for _ in range(10):
            run(fly, 10)
            angles.append(fly.joint_angles[LEGS.index("LH"), tibia])

        # a quarter period in, the tibia is near its peak; at the half period, back near the start
        start = fly.leg_overrides[0].posture[tibia]
        assert angles[4] - start == pytest.approx(math.radians(20.0), abs=0.15)
        assert angles[9] - start == pytest.approx(0.0, abs=0.15)

    def test_a_limp_leg_gets_no_torque(self):
        limp = LegOverrideConfig(leg="left_hind", mode="limp", start=0.0, duration=100.0)
        fly = body(leg_overrides=(limp,))
        torques = np.full(42, 10.0)

        joints, grip, acting = fly.perturb(torques, np.ones(6))

        leg = LEGS.index("LH")
        assert acting
        np.testing.assert_array_equal(joints.reshape(6, 7)[leg], 0.0)
        assert grip[leg] == pytest.approx(0.0)
        others = np.delete(np.arange(6), leg)
        np.testing.assert_array_equal(joints.reshape(6, 7)[others], 10.0)


class TestReplayFrames:
    def test_frames_hold_the_body_every_frame_ms(self):
        push = ForceConfig(segment="thorax", force=(0.0, 5.0, 0.0), start=50.0, duration=50.0)
        lift = LegOverrideConfig(leg="left_front", mode="lift", start=60.0, duration=20.0)
        fly = body(forces=(push,), leg_overrides=(lift,), frame_ms=10.0)

        run(fly, 100)

        # one as it starts, then one every 10 ms of the 100 run
        assert len(fly.frames) == 11
        last = fly.frames[-1]
        # the thorax's frame (position and orientation), which sits within a mm of its centre of
        # mass (the body's position), and 11 joints a leg, coxa to the last tarsus
        assert len(last["thorax"]) == 7
        assert np.linalg.norm(np.subtract(last["thorax"][:3], fly.position)) < 1.0
        assert len(last["joints"]) == 11 * len(LEGS)
        # the push acts from 50 ms, at the thorax: 5 μN to the fly's left
        assert fly.frames[4]["forces"] == [None]
        anchor_and_force = np.asarray(fly.frames[5]["forces"][0])
        assert np.linalg.norm(anchor_and_force[:3] - fly.frames[5]["thorax"][:3]) < 1.0
        assert np.linalg.norm(anchor_and_force[3:]) == pytest.approx(5.0)
        assert anchor_and_force[4] > 4.5
        assert [frame["overrides"] for frame in fly.frames[5:9]] == [
            [False],
            [True],
            [True],
            [False],
        ]
        assert all(frame["upright"] for frame in fly.frames)

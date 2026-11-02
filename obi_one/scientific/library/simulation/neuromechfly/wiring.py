"""How the body and the circuit's neurons drive each other, as the circuit's body interface says.

``Senses`` gives each sensory neuron the firing rate its sense sets from the body's state: an odour
receptor neuron the odour at its own organ, a proprioceptor its own joint, a bristle its own leg's
contact. ``Muscles`` turns the motor neurons' spikes into each muscle's activation, and the
activations into torques on the joints and the legs' grip. Nothing else joins the two.
"""

import numpy as np
from bluepysnap.nodes import NodePopulation

from obi_one.scientific.library.simulation.neuromechfly.body import BodyState
from obi_one.scientific.library.simulation.neuromechfly.interface import (
    BODY_INPUT,
    BODY_OUTPUT,
    JOINTS,
    LEGS,
    BodyInterface,
    CampaniformSense,
    ClawSense,
    ClubSense,
    HairPlateSense,
    HookSense,
    OdourSense,
    Response,
    Sensing,
    TouchSense,
    channels,
    tunings,
)

# flygym's odour sensors, in order.
ODOUR_SENSORS = (
    ("maxillary_palp", "left"),
    ("maxillary_palp", "right"),
    ("antenna", "left"),
    ("antenna", "right"),
)
# The joint each hair plate rests on: the body-coxa joint or the coxa-trochanter joint.
HAIR_PLATE_JOINTS = {"coxa": "Coxa", "trochanter": "Femur"}
TIBIA = JOINTS.index("Tibia")


def scaled(response: Response, share: np.ndarray) -> np.ndarray:
    """``response``'s rate at ``share`` (0 to 1) of full stimulation."""
    return response.spontaneous + (response.maximum - response.spontaneous) * np.clip(share, 0, 1)


class SenseGroup:
    """Neurons of one kind of sense, by node id, and their legs where they have one."""

    def __init__(self, ids: np.ndarray, legs: np.ndarray, response: Response) -> None:
        """``legs`` holds each neuron's leg (index into LEGS), or -1."""
        self.ids = np.asarray(ids, dtype=np.int64)
        self.legs = np.asarray(legs, dtype=int)
        self.response = response

    def share(self, state: BodyState) -> np.ndarray:
        """How fully each neuron is stimulated, 0 to 1."""
        raise NotImplementedError

    def rates(self, state: BodyState) -> np.ndarray:
        """Each neuron's firing rate (Hz)."""
        return scaled(self.response, self.share(state))


class OdourReceptors(SenseGroup):
    """Olfactory receptor neurons: each the odour of its class at its own organ (Hill function)."""

    def __init__(
        self, ids: np.ndarray, sensors: np.ndarray, classes: np.ndarray, response: OdourSense
    ) -> None:
        """``sensors`` indexes ODOUR_SENSORS; ``classes`` names each neuron's odour class."""
        super().__init__(ids, np.full(len(ids), -1), response)
        self.sensors = np.asarray(sensors, dtype=int)
        self.classes = np.asarray(classes, dtype=object)
        self.odour = response

    def share(self, state: BodyState) -> np.ndarray:
        """The Hill function of the intensity of its class at its sensor."""
        intensity = np.zeros(len(self.ids))
        for row, name in enumerate(state.odour_classes):
            mine = self.classes == name
            intensity[mine] = state.odour[row, self.sensors[mine]]
        h, k = self.odour.hill, self.odour.half_intensity
        return intensity**h / (intensity**h + k**h)


class Claws(SenseGroup):
    """Femoral chordotonal claw neurons: each tuned to its tibia's angle around its preference."""

    def __init__(
        self, ids: np.ndarray, legs: np.ndarray, preferred: np.ndarray, response: ClawSense
    ) -> None:
        """``preferred`` is each neuron's preferred tibia angle (radians)."""
        super().__init__(ids, legs, response)
        self.preferred = np.asarray(preferred, dtype=float)
        self.width = response.tuning_width

    def share(self, state: BodyState) -> np.ndarray:
        """A Gaussian of the tibia angle's distance from the preference."""
        angle = state.angles[self.legs, TIBIA]
        return np.exp(-((angle - self.preferred) ** 2) / (2 * self.width**2))


class Hooks(SenseGroup):
    """Femoral chordotonal hook neurons: each its tibia moving in its own direction."""

    def __init__(
        self, ids: np.ndarray, legs: np.ndarray, directions: np.ndarray, response: HookSense
    ) -> None:
        """``directions`` is +1 (flexion) or -1 (extension) for each neuron; NaN counts as +1."""
        super().__init__(ids, legs, response)
        self.directions = np.nan_to_num(np.asarray(directions, dtype=float), nan=1.0)
        self.saturation = response.saturation_speed

    def share(self, state: BodyState) -> np.ndarray:
        """The tibia's angular velocity in the neuron's direction, over the saturation speed."""
        return state.velocities[self.legs, TIBIA] * self.directions / self.saturation


class Clubs(SenseGroup):
    """Femoral chordotonal club neurons: vibration, as the tibia's angular acceleration."""

    def __init__(self, ids: np.ndarray, legs: np.ndarray, response: ClubSense) -> None:
        """Ibid."""
        super().__init__(ids, legs, response)
        self.saturation = response.saturation_acceleration

    def share(self, state: BodyState) -> np.ndarray:
        """The tibia's angular acceleration, either way, over the saturation acceleration."""
        return np.abs(state.accelerations[self.legs, TIBIA]) / self.saturation


class HairPlates(SenseGroup):
    """Hair plate neurons: their joint deflected from the standing pose, either way."""

    def __init__(
        self, ids: np.ndarray, legs: np.ndarray, joints: np.ndarray, response: HairPlateSense
    ) -> None:
        """``joints`` indexes JOINTS: the joint each plate rests on."""
        super().__init__(ids, legs, response)
        self.joints = np.asarray(joints, dtype=int)
        self.saturation = response.saturation_angle

    def share(self, state: BodyState) -> np.ndarray:
        """The joint's deflection from the standing pose, over the saturation angle."""
        bend = state.angles[self.legs, self.joints] - state.rest[self.legs, self.joints]
        return np.abs(bend) / self.saturation


class Campaniforms(SenseGroup):
    """Leg campaniform sensilla neurons: the load on their leg."""

    def __init__(self, ids: np.ndarray, legs: np.ndarray, response: CampaniformSense) -> None:
        """Ibid."""
        super().__init__(ids, legs, response)
        self.saturation = response.saturation_force

    def share(self, state: BodyState) -> np.ndarray:
        """The leg's contact forces over the saturation force."""
        return state.load[self.legs] / self.saturation


class Bristles(SenseGroup):
    """Leg bristle neurons: their leg's contact changing (they adapt to steady contact)."""

    def __init__(self, ids: np.ndarray, legs: np.ndarray, response: TouchSense) -> None:
        """Ibid."""
        super().__init__(ids, legs, response)
        self.saturation = response.saturation_change

    def share(self, state: BodyState) -> np.ndarray:
        """The rate of change of the leg's contact forces, either way, over the saturation."""
        return np.abs(state.load_change[self.legs]) / self.saturation


# Where each sense's neurons are, as their ``body_input`` labels say after the sense's name.
Found = list[tuple[np.ndarray, list[str]]]


def gathered(found: Found, place) -> tuple[np.ndarray, np.ndarray]:  # ruff: ignore[missing-type-function-argument]
    """A sense's node ids, and ``place(where)`` for each neuron, from its labels."""
    ids = np.concatenate([np.zeros(0, dtype=np.int64)] + [ids for ids, _ in found])
    return ids, np.array([place(where) for ids, where in found for _ in ids])


def leg_of(where: list[str]) -> int:
    """The leg (index into LEGS) a label names first."""
    return LEGS.index(where[0])


def odour_group(found: Found, tuning: np.ndarray, sensing: Sensing) -> SenseGroup:  # ruff: ignore[unused-function-argument]
    """``odour/<organ>/<side>/<class>``."""
    ids, places = gathered(found, lambda w: (ODOUR_SENSORS.index((w[0], w[1])), w[2]))
    return OdourReceptors(ids, places[:, 0].astype(int), places[:, 1], sensing.odour)


def claw_group(found: Found, tuning: np.ndarray, sensing: Sensing) -> SenseGroup:
    """``chordotonal/<leg>/claw``, with each neuron's preferred tibia angle as its tuning."""
    ids, legs = gathered(found, leg_of)
    return Claws(ids, legs, tuning[ids], sensing.claw)


def hook_group(found: Found, tuning: np.ndarray, sensing: Sensing) -> SenseGroup:
    """``chordotonal/<leg>/hook``, with each neuron's direction as its tuning."""
    ids, legs = gathered(found, leg_of)
    return Hooks(ids, legs, tuning[ids], sensing.hook)


def club_group(found: Found, tuning: np.ndarray, sensing: Sensing) -> SenseGroup:  # ruff: ignore[unused-function-argument]
    """``chordotonal/<leg>/club``."""
    ids, legs = gathered(found, leg_of)
    return Clubs(ids, legs, sensing.club)


def hair_plate_group(found: Found, tuning: np.ndarray, sensing: Sensing) -> SenseGroup:  # ruff: ignore[unused-function-argument]
    """``hair_plate/<leg>/<coxa or trochanter>``."""
    ids, places = gathered(
        found, lambda w: (LEGS.index(w[0]), JOINTS.index(HAIR_PLATE_JOINTS[w[1]]))
    )
    return HairPlates(ids, places[:, 0], places[:, 1], sensing.hair_plate)


def campaniform_group(found: Found, tuning: np.ndarray, sensing: Sensing) -> SenseGroup:  # ruff: ignore[unused-function-argument]
    """``campaniform/<leg>``."""
    ids, legs = gathered(found, leg_of)
    return Campaniforms(ids, legs, sensing.campaniform)


def touch_group(found: Found, tuning: np.ndarray, sensing: Sensing) -> SenseGroup:  # ruff: ignore[unused-function-argument]
    """``touch/<leg>``."""
    ids, legs = gathered(found, leg_of)
    return Bristles(ids, legs, sensing.touch)


SENSE_GROUPS = {
    "odour": odour_group,
    "claw": claw_group,
    "hook": hook_group,
    "club": club_group,
    "hair_plate": hair_plate_group,
    "campaniform": campaniform_group,
    "touch": touch_group,
}


class Senses:
    """The sensory neurons the body drives (``body_input``), and the rate each fires at."""

    def __init__(self, population: NodePopulation, interface: BodyInterface) -> None:
        """Read each sensory neuron's sense, and its tuning, from the circuit's node properties."""
        found: dict[str, Found] = {}
        for label, ids in channels(population, BODY_INPUT).items():
            kind, *where = label.split("/")
            # The chordotonal organs' kinds (claw, hook, club) are senses of their own.
            sense = where.pop() if kind == "chordotonal" else kind
            found.setdefault(sense, []).append((ids, where))
        unknown = set(found) - set(SENSE_GROUPS)
        if unknown:
            msg = f"The body interface names senses the body has none of: {sorted(unknown)}."
            raise ValueError(msg)
        tuning = tunings(population)
        self.groups = [
            make(found[sense], tuning, interface.sensing)
            for sense, make in SENSE_GROUPS.items()
            if sense in found
        ]
        #: Every sensory neuron, in the order of the rates.
        self.ids = np.concatenate([np.zeros(0, dtype=np.int64)] + [g.ids for g in self.groups])
        #: Their rates with nothing to sense (Hz).
        self.spontaneous = np.concatenate(
            [np.zeros(0)] + [np.full(len(g.ids), g.response.spontaneous) for g in self.groups]
        )

    def rates(self, state: BodyState) -> np.ndarray:
        """Each sensory neuron's firing rate (Hz) for the body's ``state``, in ``ids`` order."""
        return np.concatenate([np.zeros(0)] + [group.rates(state) for group in self.groups])


class Muscles:
    """The motor neurons the body reads (``body_output``), and what their muscles do.

    A muscle's activation follows the mean firing rate of its motor neurons, with a time constant,
    full at the interface's saturation rate: each spike adds ``increments`` to it.
    """

    def __init__(self, population: NodePopulation, interface: BodyInterface) -> None:
        """Match each motor neuron's muscle to the interface's muscle table."""
        motor = interface.motor
        legs, names, muscles, groups = [], [], [], []
        for label, ids in channels(population, BODY_OUTPUT).items():
            kind, leg, name = label.split("/")
            muscle = interface.muscles.get(leg, {}).get(name)
            if kind != "muscle" or leg not in LEGS or muscle is None:
                msg = (
                    f"Motor neurons drive '{label}', which the body interface's muscle table "
                    "does not name."
                )
                raise ValueError(msg)
            legs.append(LEGS.index(leg))
            names.append(f"{leg}/{name}")
            muscles.append(muscle)
            groups.append(ids)
        #: Each muscle's leg and name, as the activations are ordered.
        self.names = names
        tau = motor.activation_time_constant / 1000
        self.neuron_ids = np.concatenate([np.zeros(0, dtype=np.int64), *groups])
        self.unit_of_neuron = np.concatenate(
            [np.zeros(0, dtype=np.int64)]
            + [np.full(len(ids), unit) for unit, ids in enumerate(groups)]
        )
        self.increments = np.concatenate(
            [np.zeros(0)]
            + [np.full(len(ids), 1 / (len(ids) * motor.saturation_rate * tau)) for ids in groups]
        )
        self.time_constant_ms = motor.activation_time_constant
        self.torque_limit = motor.joint_torque_limit
        self.torque = np.zeros((len(LEGS) * len(JOINTS), len(groups)))
        self.grip = np.zeros((len(LEGS), len(groups)))
        for unit, (leg, muscle) in enumerate(zip(legs, muscles, strict=True)):
            if muscle.grip:
                self.grip[leg, unit] = 1.0
            strength = muscle.max_torque or motor.max_torque
            for action in muscle.actions:
                self.torque[leg * len(JOINTS) + JOINTS.index(action.joint), unit] += (
                    action.weight * strength
                )
        # A leg with several grip muscles grips by their mean activation.
        counts = self.grip.sum(axis=1, keepdims=True)
        self.grip = np.divide(self.grip, counts, out=np.zeros_like(self.grip), where=counts > 0)

    def drive(self, activation: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The joint torques (LEGS by JOINTS, flattened) and grips for the muscles' activations."""
        active = np.clip(np.asarray(activation, dtype=float), 0, 1)
        # einsum rather than @: macOS's Accelerate BLAS warns of a divide by zero on these
        # products (numpy 2.0) though they come out right.
        torques = np.einsum("ij,j->i", self.torque, active)
        grip = np.einsum("ij,j->i", self.grip, active)
        return np.clip(torques, -self.torque_limit, self.torque_limit), np.clip(grip, 0, 1)

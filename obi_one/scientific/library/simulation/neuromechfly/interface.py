"""A circuit's body interface: which of its neurons the NeuroMechFly body drives and reads, and how.

The circuit carries it in two parts:
- node properties placing each neuron in the body. ``body_input`` names the sense a sensory neuron
  carries (``odour/antenna/left/yeasty_volatile``, ``chordotonal/LF/claw``, ...), ``body_output``
  the muscle a motor neuron drives (``muscle/LF/tibia_flexor_muscle``), and ``body_tuning`` holds
  a number some senses need per neuron: a claw neuron's preferred tibia angle (radians), a hook
  neuron's direction (+1 flexion, -1 extension). Neurons outside the interface hold the fill value.
- the file named by ``components.body_interface_file`` in ``circuit_config.json``
  (``BodyInterface``): what each muscle does to the body's joints, and how the senses and muscles
  turn the body's state into firing rates and firing rates into torques.

Nothing else joins the circuit to the body: the odour reaches the brain only through the receptor
neurons at the antennae and palps, and the legs move only as the motor neurons drive their muscles.
"""

import json
from pathlib import Path
from typing import Literal

import bluepysnap
import numpy as np
from bluepysnap.nodes import NodePopulation
from pydantic import BaseModel, ConfigDict, Field, NonNegativeFloat, PositiveFloat

BODY_INPUT = "body_input"
BODY_OUTPUT = "body_output"
BODY_TUNING = "body_tuning"
INTERFACE_COMPONENT = "body_interface_file"
INTERFACE_VERSION = 2

# flygym's legs and the actuated joints of each, in its order.
LEGS = ("LF", "LM", "LH", "RF", "RM", "RH")
JOINTS = ("Coxa", "Coxa_roll", "Coxa_yaw", "Femur", "Femur_roll", "Tibia", "Tarsus1")
Joint = Literal["Coxa", "Coxa_roll", "Coxa_yaw", "Femur", "Femur_roll", "Tibia", "Tarsus1"]
# The odour classes BANC annotates its olfactory receptor neurons with (cell_function_detailed).
OdourClass = Literal[
    "yeasty_volatile",
    "fruity_volatile",
    "alcoholic_fermentation_volatile",
    "decaying_fruit_volatile",
    "plant_matter_volatile",
    "animal_matter_volatile",
    "carbon_dioxide_volatile",
    "aversive_volatile",
    "pheromone_volatile",
]


class Response(BaseModel):
    """A sense's firing rate: ``spontaneous`` at rest, up to ``maximum`` at full stimulation."""

    model_config = ConfigDict(extra="forbid")

    spontaneous: NonNegativeFloat = Field(description="Hz")
    maximum: PositiveFloat = Field(description="Hz")


class OdourSense(Response):
    """An odour receptor neuron: the odour at its own organ, through a Hill function."""

    spontaneous: NonNegativeFloat = 2.0
    maximum: PositiveFloat = 200.0
    half_intensity: PositiveFloat = Field(
        default=0.02, description="Odour intensity at half the maximum rate (flygym's units)."
    )
    hill: PositiveFloat = 1.0


class ClawSense(Response):
    """A femoral chordotonal claw neuron: tuned to the tibia's angle around its own preference."""

    spontaneous: NonNegativeFloat = 1.0
    maximum: PositiveFloat = 150.0
    tuning_width: PositiveFloat = Field(default=0.25, description="radians (Gaussian sigma)")


class HookSense(Response):
    """A femoral chordotonal hook neuron: the tibia moving in its own direction."""

    spontaneous: NonNegativeFloat = 1.0
    maximum: PositiveFloat = 150.0
    saturation_speed: PositiveFloat = Field(default=10.0, description="radians/s")


class ClubSense(Response):
    """A femoral chordotonal club neuron: vibration, read as the tibia's angular acceleration."""

    spontaneous: NonNegativeFloat = 1.0
    maximum: PositiveFloat = 150.0
    saturation_acceleration: PositiveFloat = Field(default=2000.0, description="radians/s²")


class HairPlateSense(Response):
    """A hair plate neuron: its joint deflected from the standing pose, either way."""

    spontaneous: NonNegativeFloat = 0.0
    maximum: PositiveFloat = 150.0
    saturation_angle: PositiveFloat = Field(default=0.3, description="radians")


class CampaniformSense(Response):
    """A leg campaniform sensillum neuron: the load on its leg (its contact forces)."""

    spontaneous: NonNegativeFloat = 1.0
    maximum: PositiveFloat = 150.0
    saturation_force: PositiveFloat = Field(default=10.0, description="μN")


class TouchSense(Response):
    """A leg bristle neuron: its leg's contact changing. Bristles adapt fast, so steady contact,
    as when the fly stands still, leaves them quiet.
    """

    spontaneous: NonNegativeFloat = 0.0
    maximum: PositiveFloat = 100.0
    saturation_change: PositiveFloat = Field(
        default=200.0, description="μN/s of change in the leg's contact force"
    )


class Sensing(BaseModel):
    """How each sense turns the body's state into the firing rate of its neurons."""

    model_config = ConfigDict(extra="forbid")

    odour: OdourSense = Field(default_factory=OdourSense)
    claw: ClawSense = Field(default_factory=ClawSense)
    hook: HookSense = Field(default_factory=HookSense)
    club: ClubSense = Field(default_factory=ClubSense)
    hair_plate: HairPlateSense = Field(default_factory=HairPlateSense)
    campaniform: CampaniformSense = Field(default_factory=CampaniformSense)
    touch: TouchSense = Field(default_factory=TouchSense)
    receptor_kick: PositiveFloat = Field(
        default=68.75,
        description="mV per Poisson event: enough to fire the sensory neuron, so it fires at the "
        "rate its sense sets.",
    )


class Motor(BaseModel):
    """How motor neurons drive muscles, and the joints' own passive properties."""

    model_config = ConfigDict(extra="forbid")

    saturation_rate: PositiveFloat = Field(
        default=100.0,
        description="Hz: the mean rate of a muscle's motor neurons at full activation.",
    )
    activation_time_constant: PositiveFloat = Field(
        default=20.0, description="ms: how fast a muscle's activation follows its motor neurons."
    )
    max_torque: PositiveFloat = Field(
        default=20.0, description="μN·mm a muscle exerts at full activation, unless it says."
    )
    joint_torque_limit: PositiveFloat = Field(
        default=65.0, description="μN·mm: the most all the muscles of a joint can exert together."
    )
    passive_stiffness: NonNegativeFloat = Field(
        default=20.0,
        description="μN·mm/radian pulling each joint towards the standing pose: the passive "
        "elasticity of the joint and its muscles. At 20 the fly stands, sagging a little, when its "
        "motor neurons are silent; at 0 only its muscles hold it up.",
    )
    passive_damping: NonNegativeFloat = Field(default=0.5, description="μN·mm·s/radian")


class JointAction(BaseModel):
    """A share of a muscle's torque on one joint; its sign is the direction."""

    model_config = ConfigDict(extra="forbid")

    joint: Joint
    weight: float


class Muscle(BaseModel):
    """What a muscle does when its motor neurons fire: torques on joints, or the leg's grip."""

    model_config = ConfigDict(extra="forbid")

    actions: tuple[JointAction, ...] = ()
    grip: bool = Field(
        default=False, description="Sets the leg's adhesion instead (the long tendon muscle)."
    )
    max_torque: PositiveFloat | None = Field(default=None, description="μN·mm; Motor's if unset.")
    note: str = ""


MatrixRow = tuple[float, float, float, float]


class BodyInterface(BaseModel):
    """The rules of a circuit's body interface (its ``body_interface_file``)."""

    model_config = ConfigDict(extra="forbid")

    body: str = "NeuroMechFly (flygym 1.2.1)"
    version: Literal[2] = INTERFACE_VERSION
    sensing: Sensing = Field(default_factory=Sensing)
    motor: Motor = Field(default_factory=Motor)
    muscles: dict[str, dict[str, Muscle]] = Field(
        default_factory=dict,
        description="Each leg's muscles (LF ... RH), by the name motor neurons give in "
        "body_output.",
    )
    placement: tuple[MatrixRow, MatrixRow, MatrixRow, MatrixRow] | None = Field(
        default=None,
        description="Where the circuit sits in the body, for display only: a 4x4 matrix, by rows, "
        "from circuit coordinates (um) to the body's frame (mm; +x forward, +y left, +z up, the "
        "fly standing at the origin).",
    )


def interface_problem(circuit: bluepysnap.Circuit) -> str | None:
    """Why ``circuit`` cannot drive the body, or None if it can.

    Needs only the circuit config and the nodes, so it works on a circuit staged nodes-only.
    """
    if INTERFACE_COMPONENT not in circuit.config.get("components", {}):
        return f"its circuit config names no components.{INTERFACE_COMPONENT}"
    for population in circuit.nodes.values():
        missing = {BODY_INPUT, BODY_OUTPUT} - set(population.property_names)
        if missing:
            return f"population '{population.name}' lacks the node properties {sorted(missing)}"
    return None


def read_body_interface(circuit: bluepysnap.Circuit, circuit_config_path: Path) -> BodyInterface:
    """Read the body interface rules of a fully staged circuit."""
    problem = interface_problem(circuit)
    if problem is not None:
        msg = f"The circuit has no body interface: {problem}."
        raise ValueError(msg)
    path = Path(circuit.config["components"][INTERFACE_COMPONENT])
    if not path.is_absolute():
        path = Path(circuit_config_path).parent / path
    content = json.loads(path.read_text(encoding="utf-8"))
    if content.get("version") != INTERFACE_VERSION:
        msg = (
            f"The circuit's body interface is version {content.get('version', 1)}: it joins the "
            "circuit to the body through hand-made rules (a stepping controller and a steering "
            f"rule), which the closed loop no longer has. It needs version {INTERFACE_VERSION}, "
            "which wires the receptor, proprioceptive and motor neurons to the body."
        )
        raise ValueError(msg)
    return BodyInterface.model_validate(content)


def channels(population: NodePopulation, prop: str) -> dict[str, np.ndarray]:
    """Node ids by their ``prop`` (body_input or body_output) label, neurons outside it left out."""
    values = population.get(properties=prop)
    labelled = values[values.astype(str).str.contains("/", regex=False)]
    return {
        str(label): np.sort(ids.index.to_numpy()).astype(np.int64)
        for label, ids in labelled.groupby(labelled.astype(str))
    }


def tunings(population: NodePopulation) -> np.ndarray:
    """Every neuron's ``body_tuning``: NaN where it has none, or the circuit lacks the property."""
    if BODY_TUNING not in population.property_names:
        return np.full(population.size, np.nan)
    return population.get(properties=BODY_TUNING).to_numpy(dtype=float)

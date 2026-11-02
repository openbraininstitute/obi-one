"""Brian2 simulations of a point-neuron circuit in the NeuroMechFly body, in closed loop.

The circuit must carry a body interface: which neurons the body drives and reads, and how
(``obi_one.scientific.library.simulation.neuromechfly.interface``). The config is the experiment:
the arena, pushes and leg overrides. The generated SONATA config has a ``neuromechfly`` section,
which sends the simulation to the closed-loop launch task instead of the plain Brian2 one. The
network and the body run together for ``tstop``, and stimuli and recordings are timed on that clock.
"""

from typing import Annotated, ClassVar, override

from pydantic import Field, NonNegativeFloat, PositiveFloat

from obi_one.core.exception import ConfigValidationError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.neuromechfly.closed_loop import OdourArena
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import MIN_SIMULATION_LENGTH_MILLISECONDS
from obi_one.scientific.library.simulation.neuromechfly.config import SECTION, ClosedLoopConfig
from obi_one.scientific.library.simulation.neuromechfly.interface import interface_problem
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BlockGroup,
    SimulationSingleConfigMixin,
)
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationScanConfig,
)
from obi_one.scientific.unions_and_references.neuromechfly import (
    BodyForceReference,
    BodyForceUnion,
    LegOverrideReference,
    LegOverrideUnion,
    OdourSourceReference,
    OdourSourceUnion,
    WallReference,
    WallUnion,
)

# The closed-loop job is sized for 30 s.
MAX_EPISODE_MILLISECONDS = 30000.0
EpisodeLength = Annotated[
    NonNegativeFloat, Field(ge=MIN_SIMULATION_LENGTH_MILLISECONDS, le=MAX_EPISODE_MILLISECONDS)
]


class Brian2NeuroMechFlySimulationScanConfig(Brian2CircuitSimulationScanConfig):
    """A Brian2 point-neuron circuit wired to the NeuroMechFly body (flygym) in an odour arena.

    The odour at each antenna and palp drives the circuit's olfactory receptor neurons there; its
    leg motor neurons drive the leg muscles, the only thing that moves the legs; and its leg
    proprioceptors and bristles feel the joints and the floor. Network and body exchange every
    millisecond, as the circuit's body interface wires them. There is no stepping controller: if
    the fly walks, its circuit makes it. The network runs at 0.1 ms, as Shiu et al.'s did.
    """

    name: ClassVar[str] = "Brian2 NeuroMechFly Closed-Loop Simulation Campaign"
    description: ClassVar[str] = (
        "A Brian2 point-neuron circuit wired to the NeuroMechFly body in an odour arena"
    )
    _timestep: ClassVar[PositiveFloat] = 0.1

    json_schema_extra_additions: ClassVar[dict] = {
        **Brian2CircuitSimulationScanConfig.json_schema_extra_additions,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP_BLOCK_GROUP,
            BlockGroup.BODY_BLOCK_GROUP,
            BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            BlockGroup.DISTRIBUTIONS_BLOCK_GROUP,
            BlockGroup.CIRCUIT_MANIPULATIONS_GROUP,
            BlockGroup.EVENTS_GROUP,
        ],
    }

    class Initialize(Brian2CircuitSimulationScanConfig.Initialize):
        """Initialization of the network and of the closed loop."""

        simulation_length: EpisodeLength | Annotated[list[EpisodeLength], Field(min_length=1)] = (
            Field(
                default=3000.0,
                title="Duration",
                description="Time the network and the body run together (ms).",
                json_schema_extra={
                    SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                    SchemaKey.UNITS: Units.MILLISECONDS,
                },
            )
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    arena: OdourArena = Field(
        default_factory=OdourArena,
        title="Arena",
        description="The flat arena the fly walks in.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.BODY_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    odour_sources: dict[str, OdourSourceUnion] = Field(
        default_factory=dict,
        title="Odour Sources",
        description="Where the odour comes from: at least one.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [OdourSourceReference.__name__],
            SchemaKey.SINGULAR_NAME: "Odour Source",
            SchemaKey.GROUP: BlockGroup.BODY_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    walls: dict[str, WallUnion] = Field(
        default_factory=dict,
        title="Walls",
        description="Obstacles in the arena.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [WallReference.__name__],
            SchemaKey.SINGULAR_NAME: "Wall",
            SchemaKey.GROUP: BlockGroup.BODY_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 2,
        },
    )
    forces: dict[str, BodyForceUnion] = Field(
        default_factory=dict,
        title="Body Forces",
        description="Pushes on the body during the episode.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [BodyForceReference.__name__],
            SchemaKey.SINGULAR_NAME: "Body Force",
            SchemaKey.GROUP: BlockGroup.BODY_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 3,
        },
    )
    leg_overrides: dict[str, LegOverrideUnion] = Field(
        default_factory=dict,
        title="Leg Overrides",
        description="Legs taken from their muscles during the episode, as if held by hand: "
        "held, lifted, limp or swung. Where two take the same leg at once, the later one wins.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [LegOverrideReference.__name__],
            SchemaKey.SINGULAR_NAME: "Leg Override",
            SchemaKey.GROUP: BlockGroup.BODY_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 4,
        },
    )

    @override
    def validate_circuit(self, circuit: Circuit | None) -> None:
        """Refuse a circuit with no body interface: nothing would join it to the body."""
        super().validate_circuit(circuit)
        if circuit is None:
            return
        problem = interface_problem(circuit.sonata_circuit)
        if problem is not None:
            msg = (
                f"Circuit '{circuit.name}' is not connected to a body: {problem}. A NeuroMechFly "
                "simulation needs a circuit with a body interface (node properties body_input "
                "and body_output, and a body_interface_file)."
            )
            raise ConfigValidationError(msg)

    def closed_loop_config(self) -> ClosedLoopConfig:
        """The ``neuromechfly`` section this config generates."""
        if not self.odour_sources:
            msg = "Add at least one Odour Source."
            raise ConfigValidationError(msg)
        return ClosedLoopConfig(
            arena=self.arena.section(list(self.odour_sources.values()), list(self.walls.values())),
            forces=tuple(force.config() for force in self.forces.values()),
            leg_overrides=tuple(override.config() for override in self.leg_overrides.values()),
        )

    def base_sonata_config(self, sonata_config: dict | None = None) -> dict:
        """Add the closed loop: the network and the body run together for the duration."""
        sonata_config = super().base_sonata_config(sonata_config)
        sonata_config[SECTION] = self.closed_loop_config().model_dump(mode="json")
        return sonata_config


class Brian2NeuroMechFlySimulationSingleConfig(
    Brian2NeuroMechFlySimulationScanConfig, SimulationSingleConfigMixin
):
    """Only allows single values."""

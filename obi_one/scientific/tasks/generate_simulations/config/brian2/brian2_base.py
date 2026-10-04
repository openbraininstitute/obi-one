import abc
from typing import ClassVar, override

from libsonata import SimulatorType
from pydantic import Field, PositiveFloat

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.specific import AllPointNeurons
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    SIMULATION_TIMESTEP_MILLISECONDS,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
    BlockGroup,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    PointNeuronSetReference,
)
from obi_one.scientific.unions_and_references.recordings import (
    Brian2RecordingUnion,
    RecordingReference,
)
from obi_one.scientific.unions_and_references.timestamps import (
    TimestampsReference,
    TimestampsUnion,
)


class Brian2SimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for Brian2-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.Brian2
    _timestep: ClassVar[PositiveFloat] = SIMULATION_TIMESTEP_MILLISECONDS

    # Every untargeted block -- the simulation itself, recordings, stimuli and manipulations --
    # falls back to this one default, which the generation task fills in.
    default_node_set_name: ClassVar[str] = "Default: All Point Neurons"
    default_neuron_set_type: ClassVar[type[AllPointNeurons]] = AllPointNeurons

    @property
    def default_neuron_set_reference(self) -> PointNeuronSetReference:
        """The default neuron set reference for the simulation (all point neurons)."""
        ref = PointNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_node_set_name
        )
        ref.block = self.default_neuron_set_type()
        ref.block.set_block_name(self.default_node_set_name)
        return ref

    recordings: dict[str, Brian2RecordingUnion] = Field(
        default_factory=dict,
        description="Recordings for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [RecordingReference.__name__],
            SchemaKey.SINGULAR_NAME: "Recording",
            SchemaKey.GROUP: BlockGroup.STIMULI_RECORDINGS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    timestamps: dict[str, TimestampsUnion] = Field(
        default_factory=dict,
        title="Timestamps",
        description="Timestamps for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [TimestampsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Timestamps",
            SchemaKey.GROUP: BlockGroup.EVENTS_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    @override
    def validate_circuit(self, circuit: Circuit | None) -> None:
        """Refuse a circuit the Brian2 runner cannot build a network from.

        ``simulate_brian2`` asserts a single node population, so a circuit with none or several
        would only fail once the simulation ran.
        """
        if circuit is None:
            return
        populations = Circuit.get_node_population_names(
            circuit.sonata_circuit, incl_virtual=False, incl_biophysical=False
        )
        if len(populations) != 1:
            msg = (
                f"A Brian2 simulation needs exactly one point node population; "
                f"circuit '{circuit.name}' has {len(populations)}: {populations}."
            )
            raise OBIONEError(msg)

    class Initialize(BaseSimulationScanConfig.Initialize):
        pass

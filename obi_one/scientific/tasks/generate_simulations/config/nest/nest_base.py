import abc
from typing import ClassVar, override

from libsonata import SimulatorType
from pydantic import Field, PositiveFloat

from obi_one.core.exception import ConfigValidationError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.base import NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.specific import AllPointNeurons
from obi_one.scientific.blocks.recordings.soma import (
    SimulationDtTimeWindowSomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import SIMULATION_TIMESTEP_MILLISECONDS
from obi_one.scientific.library.simulation.nest import (
    connection_overrides,
    current_clamps,
    soma_reports,
)
from obi_one.scientific.library.simulation.nest.constants import (
    NEURON_TYPES,
    NODE_TYPES,
    TYPE_VIRTUAL,
)
from obi_one.scientific.tasks.generate_simulations.config.base import (
    BaseSimulationScanConfig,
    BlockGroup,
)
from obi_one.scientific.unions_and_references.neuron_sets import PointNeuronSetReference
from obi_one.scientific.unions_and_references.recordings import (
    NestRecordingUnion,
    RecordingReference,
)
from obi_one.scientific.unions_and_references.timestamps import (
    TimestampsReference,
    TimestampsUnion,
)

# A NEST multimeter keeps every sample (sender, time and potential) until the run ends, and each
# report has its own, so what a simulation holds is the sum over its reports of neurons x frames.
# Writing a report then copies the samples out of NEST, sorts them and reshapes them into a
# (neurons, frames) array.
#
# Measured with ``simulate_nest`` on circuits of unconnected ``iaf_psc_alpha`` neurons, peak RSS
# (macOS, NEST 3.10): 0.6 GB with no recording; +1.04 GB for 10,000 neurons x 1,000 frames (1e7
# samples) and +2.58 GB for 2.5e7 - about 104 bytes per sample. Larger recordings (5e7 and 1e8
# samples) measured 77 and 48 bytes per sample, but macOS compresses memory under that much
# pressure, so the 104 bytes measured without it are used.
NEST_RECORDED_SAMPLE_BYTES = 104

# The most soma-voltage samples one NEST simulation may record. 4e7 samples is 4.2 GB at 104 bytes,
# which leaves room for the network and what the job adds around the simulation within the
# machine's 8 GB.
MAX_NEST_RECORDED_SAMPLES = 40_000_000

CLAMP_MODULES = frozenset({"linear", "pulse", "sinusoidal"})


class NestSimulationScanConfig(BaseSimulationScanConfig, abc.ABC):
    """Abstract base class for NEST-based simulation scan configurations."""

    _target_simulator: ClassVar[SimulatorType] = SimulatorType.NEST
    _timestep: ClassVar[PositiveFloat] = SIMULATION_TIMESTEP_MILLISECONDS

    # The simulation, recordings, current clamps, spike targets and manipulations fall back to
    # all point neurons. Only the source of a spike stimulus defaults to the virtual neurons, see
    # `default_spike_source_population_type`.
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

    recordings: dict[str, NestRecordingUnion] = Field(
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
        """Refuse a circuit the NEST runner cannot build a network from.

        ``simulate_nest`` creates ``nest_point`` populations and replays spikes from ``virtual``
        ones, and refuses any other population type once the simulation runs.
        """
        if circuit is None:
            return
        nodes = circuit.sonata_circuit.nodes
        types = {population: nodes[population].type for population in nodes.population_names}
        unsupported = {
            population: population_type
            for population, population_type in types.items()
            if population_type not in NODE_TYPES
        }
        if unsupported:
            msg = (
                f"A NEST simulation needs 'nest_point' and 'virtual' node populations only; "
                f"circuit '{circuit.name}' has {unsupported}."
            )
            raise ConfigValidationError(msg)
        if not any(population_type in NEURON_TYPES for population_type in types.values()):
            msg = (
                f"A NEST simulation needs a 'nest_point' population; circuit '{circuit.name}' "
                "has none."
            )
            raise ConfigValidationError(msg)

    @override
    def default_spike_source_population_type(
        self, circuit: Circuit | None
    ) -> NeuronSetPopulationType | None:
        """The virtual neurons, when every virtual population projects onto a point population.

        The virtual populations of a simplified circuit are its projections, which stay silent
        unless spikes are replayed from them. A virtual population without edges onto a point
        population cannot be a replay source, so then the simulation default is kept.
        """
        if circuit is None:
            return None
        nodes, edges = circuit.sonata_circuit.nodes, circuit.sonata_circuit.edges
        virtual = [name for name in nodes.population_names if nodes[name].type == TYPE_VIRTUAL]
        projecting = {
            edges[name].source.name
            for name in edges.population_names
            if edges[name].target.type in NEURON_TYPES
        }
        if virtual and all(population in projecting for population in virtual):
            return NeuronSetPopulationType.VIRTUAL
        return None

    def _recording_frames(self, name: str, recording: NestRecordingUnion) -> soma_reports.Frames:
        """The frames the runner records for *recording*, refusing a Timestep it cannot sample."""
        start, end = 0.0, self.initialize.simulation_length
        if isinstance(
            recording,
            TimeWindowSomaVoltageRecording | SimulationDtTimeWindowSomaVoltageRecording,
        ):
            start, end = recording.start_time, min(recording.end_time, end)
        try:
            return soma_reports.Frames.of(
                name,
                start,  # ty:ignore[invalid-argument-type]
                end,  # ty:ignore[invalid-argument-type]
                recording.recording_timestep,
                self.timestep,
            )
        except ValueError as error:
            msg = f"{error} A NEST recording's Timestep must be a multiple of {self.timestep} ms."
            raise ConfigValidationError(msg) from error

    @override
    def validate_recordings(self, circuit: Circuit) -> None:
        """Refuse recordings the NEST job cannot sample or hold in memory.

        Each recording is sampled on its own Timestep, over its own window, and every sample is
        held until the simulation ends, so the samples of all recordings are added up.
        """
        samples = 0
        described = []
        for name, recording in self.recordings.items():
            frames = self._recording_frames(name, recording)
            neuron_set = recording.neuron_set or self.default_neuron_set_reference
            size = sum(len(ids) for ids in neuron_set.block.get_neuron_ids(circuit).values())
            samples += size * frames.count
            described.append(
                f"'{name}' ({size:,} neurons in '{neuron_set.block.block_name}' x "
                f"{frames.count:,} frames)"
            )

        if samples <= MAX_NEST_RECORDED_SAMPLES:
            return

        noun = "recording" if len(described) == 1 else "recordings"
        msg = (
            f"The voltage {noun} {', '.join(described)} would hold {samples:,} samples, "
            f"{samples * NEST_RECORDED_SAMPLE_BYTES / 1e9:.1f} GB, until the simulation ends. A "
            f"NEST simulation can record at most {MAX_NEST_RECORDED_SAMPLES:,} samples "
            f"({MAX_NEST_RECORDED_SAMPLES * NEST_RECORDED_SAMPLE_BYTES / 1e9:.1f} GB) and still "
            "fit in its job's memory. A recording without a neuron set records every point "
            "neuron in the circuit: record a smaller neuron set, a shorter window or a coarser "
            "Timestep, or shorten the simulation."
        )
        raise ConfigValidationError(msg)

    @override
    def validate_sonata_config(self, sonata_config: dict, circuit: Circuit | None) -> None:
        """Refuse the inputs and connection overrides the NEST runner would refuse when it runs.

        The checks are the runner's own: its parsing of the connection overrides and of a pulse
        train, and its requirement that a current clamp injects into at least one point neuron.
        """
        try:
            connection_overrides.parse_overrides(
                sonata_config.get("connection_overrides", []), self.timestep
            )
        except ValueError as error:
            raise ConfigValidationError(str(error)) from error

        for name, entry in sonata_config.get("inputs", {}).items():
            if entry["module"] == "pulse":
                window = current_clamps.Window.of(entry["delay"], entry["duration"], self.timestep)
                try:
                    current_clamps.pulse_steps(
                        entry["amp_start"],
                        entry["width"],
                        entry["frequency"],
                        entry["delay"],
                        window,
                        self.timestep,
                    )
                except ValueError as error:
                    msg = f"Stimulus '{name}': {error}"
                    raise ConfigValidationError(msg) from error
            if entry["module"] in CLAMP_MODULES and circuit is not None:
                self._check_clamp_targets_point_neurons(name, entry["node_set"], circuit)

    def _check_clamp_targets_point_neurons(
        self, name: str, node_set: str, circuit: Circuit
    ) -> None:
        nodes = circuit.sonata_circuit.nodes
        ids = self.neuron_sets[node_set].get_neuron_ids(circuit)  # ty:ignore[unresolved-attribute]
        if not any(
            len(node_ids)
            for population, node_ids in ids.items()
            if nodes[population].type in NEURON_TYPES
        ):
            msg = (
                f"Stimulus '{name}': its neuron set '{node_set}' contains no 'nest_point' "
                "neuron to inject current into."
            )
            raise ConfigValidationError(msg)

    class Initialize(BaseSimulationScanConfig.Initialize):
        pass

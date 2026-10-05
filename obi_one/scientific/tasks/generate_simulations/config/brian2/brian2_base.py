import abc
import math
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

# Brian2's StateMonitor holds every recorded sample as a float64.
BRIAN2_RECORDED_SAMPLE_BYTES = 8

# The most soma-voltage samples (recorded neurons x timesteps) one Brian2 simulation may record.
#
# ``simulate_brian2`` records the union of every report's neurons in one StateMonitor, at every
# timestep of the whole run, and holds it until the run ends. Writing a report then copies its
# rows (float64), divides out the unit into another array for the report's window (float64) and
# converts that to float32 - up to 28 bytes per sample at the peak.
#
# Measured on FlyWire-v783-Brian2-LIF (138,639 neurons, 15.1M synapses), 100 ms, peak RSS: 2.42 GB
# with no recording; +1.58 GB for 25,000 neurons (1e8 samples); +2.73 GB for 50,000 (2e8); and
# +2.14 GB for the same 25,000 written twice (whole run and a 0-50 ms window) - 14 to 21 bytes per
# sample. On staging (8 GB machine), 138,639 neurons x 4,000 timesteps (5.5e8 samples) was killed
# for running out of memory, while 1,299 x 12,000 (1.6e7) completed.
#
# 1.5e8 samples is 4.2 GB at the 28 byte worst case, which leaves room for the 2.4 GB network and
# what the job adds around the simulation within the machine's 8 GB.
MAX_BRIAN2_RECORDED_SAMPLES = 150_000_000


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

    @override
    def validate_recordings(self, circuit: Circuit) -> None:
        """Refuse recordings the Brian2 job cannot hold in memory.

        ``simulate_brian2`` records the union of every recording's neurons, for the whole run, so
        that is what is counted, whatever each recording's time window.
        """
        recorded: set[tuple[str, int]] = set()
        described = []
        for name, recording in self.recordings.items():
            neuron_set = recording.neuron_set or self.default_neuron_set_reference
            ids_by_population = neuron_set.block.get_neuron_ids(circuit)
            recorded.update(
                (population, node_id)
                for population, node_ids in ids_by_population.items()
                for node_id in node_ids
            )
            size = sum(len(node_ids) for node_ids in ids_by_population.values())
            described.append(f"'{name}' ({size:,} neurons in '{neuron_set.block.block_name}')")

        timesteps = math.ceil(self.initialize.simulation_length / self.timestep)  # ty:ignore[unsupported-operator]
        samples = len(recorded) * timesteps
        if samples <= MAX_BRIAN2_RECORDED_SAMPLES:
            return

        noun = "recording" if len(described) == 1 else "recordings"
        msg = (
            f"The voltage {noun} {', '.join(described)} would hold {len(recorded):,} "
            f"neurons at every one of the simulation's {timesteps:,} timesteps (a time window "
            f"only applies when a recording is written): {samples:,} samples, "
            f"{samples * BRIAN2_RECORDED_SAMPLE_BYTES / 1e9:.1f} GB before they are copied again "
            f"to be written. A Brian2 simulation can record at most "
            f"{MAX_BRIAN2_RECORDED_SAMPLES:,} samples "
            f"({MAX_BRIAN2_RECORDED_SAMPLES * BRIAN2_RECORDED_SAMPLE_BYTES / 1e9:.1f} GB) and "
            "still fit in its job's memory. A recording without a neuron set records every "
            "neuron in the circuit: record a smaller neuron set, or shorten the simulation."
        )
        raise OBIONEError(msg)

    class Initialize(BaseSimulationScanConfig.Initialize):
        pass

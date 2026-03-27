from abc import abstractmethod
from pathlib import Path

import h5py
import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.stimuli.stimulus import (
    _TIMESTAMPS_OFFSET_FIELD,
    StimulusWithTimestamps,
)
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_neuron_set,
    resolve_neuron_set_ref_to_node_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
    resolve_timestamps_ref_to_timestamps_block,
)

SPIKE_STIMULUS_SONATA_MODULE = "synapse_replay"
SPIKE_STIMULUS_SONATA_INPUT_TYPE = "spikes"


def check_non_none_neuron_set_reference_is_biophysical(
    neuron_set_reference: NeuronSetReference | None,
    circuit: Circuit,
    population: str | None,
    error_message: str,
) -> None:
    if (neuron_set_reference is not None) and (
        neuron_set_reference.block.population_type(circuit, population) != "biophysical"
    ):
        msg = f"{error_message}Neuron Set: '{neuron_set_reference.block.block_name}'."
        raise OBIONEError(msg)


class SpikeStimulus(StimulusWithTimestamps):
    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: True,
        },
    )

    targeted_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
            SchemaKey.SUPPORTS_VIRTUAL: True,
        },
    )

    timestamp_offset: float | list[float] = _TIMESTAMPS_OFFSET_FIELD

    """
    Misc
    """
    _source_node_population: str | None = None
    _resolved_timestamps: list[float] | None = None

    @property
    def resolved_timestamps(self) -> list[float]:
        if self._resolved_timestamps is None:
            msg = "Timestamps must be resolved before accessing. Call generate_spikes first."
            raise ValueError(msg)
        return self._resolved_timestamps

    def config(
        self,
        circuit: Circuit,
        sonata_simulation_config_directory: Path,
        simulation_length: NonNegativeFloat,
        population: str | None = None,
        default_node_set: str = "All",
        default_timestamps: TimestampsReference = None,
        source_node_population: str | None = None,
        default_source_neuron_set: NeuronSetReference | None = None,
    ) -> dict:
        check_non_none_neuron_set_reference_is_biophysical(
            neuron_set_reference=self.targeted_neuron_set,
            circuit=circuit,
            population=population,
            error_message="Target Neuron Set of Spike Stimulus must be biophysical.",
        )

        if default_timestamps is None:
            default_timestamps = SingleTimestamp(start_time=0.0)
        self._default_timestamps = default_timestamps

        """SHOULD DEAL WITH NONE CASE, OR RAISE ISSUE IF SELF.SOURCE_NEURON_SET.

        IS NONE AND DEFAULT SOURCE NEURON SET IS NONE
        if default_source_neuron_set is None:
            self._default_source_neuron_set = NeuronSetReference(
            )
        """
        source_neuron_set = resolve_neuron_set_ref_to_neuron_set(
            self.source_neuron_set, default_source_neuron_set
        )

        target_node_set = resolve_neuron_set_ref_to_node_set(
            self.targeted_neuron_set, default_node_set
        )

        spike_file_relative_path = self.generate_spikes(
            circuit=circuit,
            spike_file_directory=sonata_simulation_config_directory,
            source_neuron_set=source_neuron_set,
            source_node_population=source_node_population,
        )

        sonata_config = self._generate_config(
            spike_file_relative_path=spike_file_relative_path,
            sonata_simulation_config_directory=sonata_simulation_config_directory,
            simulation_length=simulation_length,
            target_node_set=target_node_set,
        )

        return sonata_config

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_directory: Path,
        source_neuron_set: NeuronSetReference,
        source_node_population: str | None = None,
    ) -> Path:
        source_gids = source_neuron_set.get_neuron_ids(circuit, source_node_population)
        source_node_population = source_neuron_set.get_population(source_node_population)

        # Timestamps
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )
        resolved_timestamps = timestamps_block.timestamps()

        # Generate spikes
        spikes_by_gid = self.generate_spikes_by_gid(
            source_gids=source_gids, resolved_timestamps=resolved_timestamps
        )

        # Write spikes to file
        spike_file = f"{self.block_name}_spikes.h5"
        spike_file_relative_path = Path(spike_file)
        spike_file_absolute_path = spike_file_directory / spike_file
        self.write_spike_file(spikes_by_gid, spike_file_absolute_path, source_node_population)

        return spike_file_relative_path

    def _generate_config(
        self,
        spike_file_relative_path: Path,
        sonata_simulation_config_directory: Path,
        simulation_length: NonNegativeFloat,
        target_node_set: str,
    ) -> dict:
        spike_file_absolute_path = (
            sonata_simulation_config_directory / spike_file_relative_path
        ).resolve()
        if not spike_file_absolute_path.exists():
            msg = f"Spike file not found: {spike_file_absolute_path}"
            raise FileNotFoundError(msg)

        sonata_config = {}
        sonata_config[self.block_name] = {
            "delay": 0.0,  # If present, the simulation filters out those times before the delay
            "duration": simulation_length,
            "node_set": target_node_set,
            "module": SPIKE_STIMULUS_SONATA_MODULE,
            "input_type": SPIKE_STIMULUS_SONATA_INPUT_TYPE,
            "spike_file": str(spike_file_relative_path),
        }

        return sonata_config

    @abstractmethod
    def generate_spikes_by_gid(
        self, source_gids: list[int], resolved_timestamps: list[float]
    ) -> dict[int, list[float]]:
        pass

    @staticmethod
    def write_spike_file(
        spikes_by_gid: dict[int, list[float]],
        spike_file: Path,
        source_node_population: str | None = None,
    ) -> None:
        """Writes SONATA output spike trains to file.

        Spike file format specs: https://github.com/AllenInstitute/sonata/blob/master/docs/SONATA_DEVELOPER_GUIDE.md#spike-file
        """
        out_path = Path(spike_file).parent
        if not out_path.exists():
            out_path.mkdir(parents=True)

        times = []
        gids = []
        for gid, spike_times in spikes_by_gid.items():
            times.extend(spike_times)
            gids.extend([gid] * len(spike_times))

        sort_idx = np.argsort(times, kind="stable")
        sorted_times = np.array(times, dtype=np.float64)[sort_idx]
        sorted_gids = np.array(gids, dtype=np.uint64)[sort_idx]

        with h5py.File(spike_file, "w") as f:
            pop = f.create_group(f"/spikes/{source_node_population}")
            ts = pop.create_dataset("timestamps", data=sorted_times)
            pop.create_dataset("node_ids", data=sorted_gids)
            ts.attrs["units"] = "ms"

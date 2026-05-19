from abc import abstractmethod
from pathlib import Path

import h5py
import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.stimuli.stimulus import (
    _TIMESTAMPS_OFFSET_FIELD,
    StimulusWithTimestamps,
)
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import SONATA
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_neuron_set,
)
from obi_one.scientific.unions.unions_timestamps import (
    TimestampsReference,
)


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

    def _single_timestamp_stimulus_config(self, stim_dict: dict) -> dict:  # noqa: PLR6301
        return stim_dict

    def config(
        self,
        circuit: Circuit,
        sonata_simulation_config_directory: Path,
        simulation_length: NonNegativeFloat,
        default_timestamps: TimestampsReference = None,  # ty:ignore[invalid-parameter-default]
        source_node_population: str | None = None,
        target_node_population: str | None = None,
        default_source_neuron_set_reference: NeuronSetReference | None = None,
        default_target_neuron_set_reference: NeuronSetReference | None = None,
    ) -> dict:
        if default_timestamps is None:
            default_timestamps = SingleTimestamp(start_time=0.0)
        self._default_timestamps = default_timestamps

        source_neuron_set = resolve_neuron_set_ref_to_neuron_set(
            self.source_neuron_set, default_source_neuron_set_reference
        )

        target_neuron_set = resolve_neuron_set_ref_to_neuron_set(
            self.targeted_neuron_set, default_target_neuron_set_reference
        )

        if target_neuron_set.is_biophysical(circuit, target_node_population) is False:  # ty:ignore[unresolved-attribute]
            msg = "Target Neuron Set of Spike Stimulus must be biophysical."
            raise OBIONEError(msg)

        spike_file_relative_path = self.generate_spikes(
            circuit=circuit,
            spike_file_directory=sonata_simulation_config_directory,
            source_neuron_set=source_neuron_set,  # ty:ignore[invalid-argument-type]
            source_node_population=source_node_population,
        )

        sonata_config = self._generate_config(
            spike_file_relative_path=spike_file_relative_path,
            sonata_simulation_config_directory=sonata_simulation_config_directory,
            simulation_length=simulation_length,
            target_neuron_set=target_neuron_set,  # ty:ignore[invalid-argument-type]
        )

        return sonata_config

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_directory: Path,
        source_neuron_set: NeuronSet,
        source_node_population: str | None = None,
    ) -> Path:
        source_gids = source_neuron_set.get_neuron_ids(circuit, source_node_population)
        source_node_population = source_neuron_set.get_population(source_node_population)

        # Generate spikes
        spikes_by_gid = self.generate_spikes_by_gid(source_gids=source_gids)  # ty:ignore[invalid-argument-type]

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
        target_neuron_set: NeuronSet,
    ) -> dict:  # ty:ignore[invalid-method-override]
        spike_file_absolute_path = (
            sonata_simulation_config_directory / spike_file_relative_path
        ).resolve()
        if not spike_file_absolute_path.exists():
            msg = f"Spike file not found: {spike_file_absolute_path}"
            raise FileNotFoundError(msg)

        sonata_config = {}
        sonata_config[self.block_name] = {
            SONATA.DELAY: 0.0,  # If present, the simulation filters times before the delay
            SONATA.DURATION: simulation_length,
            SONATA.NODE_SET: target_neuron_set.block_name,
            SONATA.MODULE: SONATA.SPIKE_STIMULUS_MODULE,
            SONATA.INPUT_TYPE: SONATA.SPIKE_STIMULUS_INPUT_TYPE,
            SONATA.SPIKE_FILE: str(spike_file_relative_path),
        }

        return sonata_config

    @abstractmethod
    def generate_spikes_by_gid(self, source_gids: list[int]) -> dict[int, list[float]]:
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

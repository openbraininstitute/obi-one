from abc import abstractmethod
from pathlib import Path
from typing import Self

import h5py
import numpy as np
from pydantic import Field, NonNegativeFloat, model_validator

from obi_one.core.exception import OBIONEError
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


class SpikeStimulus(StimulusWithTimestamps):
    _module: str = "synapse_replay"
    _input_type: str = "spikes"
    
    source_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Source)",
        description="Source neuron set to simulate",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
            "supports_virtual": True,
        },
    )

    targeted_neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Target neuron set to simulate",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
            "supports_virtual": True,
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
        spike_file_directory: Path,
        simulation_length: NonNegativeFloat,
        population: str | None = None,
        default_node_set: str = "All",
        default_timestamps: TimestampsReference = None,
        source_node_population: str | None = None,
        default_source_neuron_set: NeuronSetReference | None = None,
    ) -> dict:
        self._default_node_set = default_node_set

        if (self.targeted_neuron_set is not None) and (
            self.targeted_neuron_set.block.population_type(circuit, population) != "biophysical"
        ):
            msg = (
                f"Target Neuron Set '{self.targeted_neuron_set.block.block_name}' for "
                f"{self.__class__.__name__}: '{self.block_name}' should be biophysical!"
            )
            raise OBIONEError(msg)

        if default_timestamps is None:
            default_timestamps = SingleTimestamp(start_time=0.0)
        self._default_timestamps = default_timestamps


        spike_file_relative_path = self.generate_spikes(
            circuit=circuit,
            spike_file_directory=spike_file_directory,
            simulation_length=simulation_length,
            source_node_population=source_node_population,
            default_source_neuron_set=default_source_neuron_set,
        )

        sonata_config = self._generate_config(spike_file_relative_path,
                                              module=self._module,
                                              input_type=self._input_type,
                                              simulation_length=simulation_length)

        return sonata_config

    def _generate_config(self, 
                         spike_file_relative_path: Path,
                         module: str,
                         input_type: str,
                         simulation_length: NonNegativeFloat) -> dict:
        
        if not spike_file_relative_path.exists():
            msg = f"Spike file not found: {spike_file_relative_path}"
            raise FileNotFoundError(msg)

        sonata_config = {}
        sonata_config[self.block_name] = {
            "delay": 0.0,  # If present, the simulation filters out those times before the delay
            "duration": simulation_length,
            "node_set": resolve_neuron_set_ref_to_node_set(
                self.targeted_neuron_set, self._default_node_set
            ),
            "module": module,
            "input_type": input_type,
            "spike_file": str(spike_file_relative_path),
        }

        return sonata_config

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_directory: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
        default_source_neuron_set: NeuronSetReference | None = None,
    ) -> Path:

        """
        SHOULD DEAL WITH NONE CASE, OR RAISE ISSUE IF SELF.SOURCE_NEURON_SET
        IS NONE AND DEFAULT SOURCE NEURON SET IS NONE
        if default_source_neuron_set is None:
            self._default_source_neuron_set = NeuronSetReference(
            )
        """

        self.source_neuron_set = resolve_neuron_set_ref_to_neuron_set(
            self.source_neuron_set, default_source_neuron_set
        )

        source_gids = self.source_neuron_set.get_neuron_ids(circuit, source_node_population)
        self._source_node_population = self.source_neuron_set.get_population(source_node_population)
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )
        self._resolved_timestamps = timestamps_block.timestamps()

        spikes_by_gid = self.generate_spikes_by_gid(source_gids=source_gids)

        spike_file = f"{self.block_name}_spikes.h5"
        spike_file_relative_path = spike_file
        spike_file_absolute_path = spike_file_directory / spike_file

        self.write_spike_file(
            spikes_by_gid, spike_file_absolute_path, self._source_node_population
        )

        return spike_file_relative_path


    @abstractmethod
    def generate_spikes_by_gid(self) -> dict[int, list[float]]:
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

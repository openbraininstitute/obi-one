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
    _spike_file: Path | None = None
    _simulation_length: float | None = None
    _gids: list[int] | None = None
    _source_node_population: str | None = None
    _resolved_timestamps: list[float] | None = None

    @property
    def resolved_timestamps(self) -> list[float]:
        if self._resolved_timestamps is None:
            msg = "Timestamps must be resolved before accessing. Call generate_spikes first."
            raise ValueError(msg)
        return self._resolved_timestamps

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

    def config(
        self,
        circuit: Circuit,
        population: str | None = None,
        default_node_set: str = "All",
        default_timestamps: TimestampsReference = None,
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

        return self._generate_config()

    def _generate_config(self) -> dict:
        if self._spike_file is None:
            msg = "Spike file must be set before generating SONATA config"
            raise ValueError(msg)
        if self._simulation_length is None:
            msg = "Simulation length must be set before generating SONATA config"
            " component for SpikeStimulus."
            raise ValueError(msg)

        sonata_config = {}
        sonata_config[self.block_name] = {
            "delay": 0.0,  # If present, the simulation filters out those times before the delay
            "duration": self._simulation_length,
            "node_set": resolve_neuron_set_ref_to_node_set(
                self.targeted_neuron_set, self._default_node_set
            ),
            "module": self._module,
            "input_type": self._input_type,
            "spike_file": str(self._spike_file),  # os.path.relpath #
        }

        return sonata_config

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_path: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
        default_source_neuron_set: NeuronSetReference | None = None,
    ) -> None:
        self._default_source_neuron_set = default_source_neuron_set

        """
        SHOULD DEAL WITH NONE CASE, OR RAISE ISSUE IF SELF.SOURCE_NEURON_SET
        IS NONE AND DEFAULT SOURCE NEURON SET IS NONE
        if default_source_neuron_set is None:
            self._default_source_neuron_set = NeuronSetReference(
            )
        """

        self.source_neuron_set = resolve_neuron_set_ref_to_neuron_set(
            self.source_neuron_set, self._default_source_neuron_set
        )

        self._simulation_length = simulation_length
        self._gids = self.source_neuron_set.get_neuron_ids(circuit, source_node_population)
        self._source_node_population = self.source_neuron_set.get_population(source_node_population)
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )
        self._resolved_timestamps = timestamps_block.timestamps()

        self._pre_generate_validation()

        spikes_by_gid = self.generate_spikes_by_gid()

        self._spike_file = f"{self.block_name}_spikes.h5"
        self.write_spike_file(
            spikes_by_gid, spike_file_path / self._spike_file, self._source_node_population
        )

    def _pre_generate_validation(self) -> None:
        pass

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


class ExtendedSpikeStimulus(SpikeStimulus):
    """Base class for spike stimuli with a duration, where stimulus epochs must not overlap."""

    @model_validator(mode="after")
    def validate_no_overlap(self) -> Self:
        if self._resolved_timestamps is None:
            return self
        for idx, t in enumerate(self.resolved_timestamps[:-1]):
            end_time = t + self.timestamp_offset + self.duration
            next_timestamp = self.resolved_timestamps[idx + 1]
            if end_time >= next_timestamp:
                stimulus_name_part = f" in '{self.block_name}'" if self.has_block_name() else ""
                msg = (
                    f"Stimulus time intervals overlap{stimulus_name_part}! "
                    f"Current stimulus ends at {end_time:.2f} ms "
                    f"(timestamp {t:.2f} ms + offset {self.timestamp_offset:.2f} ms + "
                    f"duration {self.duration:.2f} ms), "
                    f"but next timestamp starts at {next_timestamp:.2f} ms. "
                    f"To fix: reduce 'duration', reduce 'timestamp_offset', "
                    f"or increase spacing between timestamps."
                )
                raise ValueError(msg)
        return self

    def _pre_generate_validation(self) -> None:
        self.validate_no_overlap()


class InstantaneousSpikeStimulus(SpikeStimulus):
    """Base class for spike stimuli without a duration."""

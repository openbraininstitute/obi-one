from pathlib import Path
from typing import Annotated, ClassVar

import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_POISSON_SPIKE_LIMIT,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_NON_NEGATIVE_FLOAT_VALUE,
)
from obi_one.scientific.unions.unions_timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)


class PoissonSpikeStimulus(SpikeStimulus):
    """Spike times drawn from a Poisson process with a given frequency.

    Sent from all neurons in the source neuron set to efferently connected

    When using repeated timestamps (i.e. Regular Timestamps), stimulus durations
    should be small enough such that stimulus periods do not overlap across
    repetitions of the same stimulus.
    """

    title: ClassVar[str] = "Poisson Spikes (Efferent)"

    _module: str = "synapse_replay"
    _input_type: str = "spikes"
    duration: (
        Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration in milliseconds for how long input is activated.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )
    frequency: (
        Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]
        | list[Annotated[NonNegativeFloat, Field(ge=_MIN_NON_NEGATIVE_FLOAT_VALUE)]]
    ) = Field(
        default=1.0,
        title="Frequency",
        description="Mean frequency (Hz) of the Poisson input.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "Hz",
        },
    )
    random_seed: int | list[int] = Field(
        default=0,
        title="Random Seed",
        description="Seed for the random number generator to ensure "
        "reproducibility of the spike generation.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )

    def generate_spikes(
        self,
        circuit: Circuit,
        spike_file_path: Path,
        simulation_length: NonNegativeFloat,
        source_node_population: str | None = None,
    ) -> None:
        self._simulation_length = simulation_length
        rng = np.random.default_rng(self.random_seed)
        gids = self.source_neuron_set.block.get_neuron_ids(circuit, source_node_population)
        source_node_population = self.source_neuron_set.block.get_population(source_node_population)
        timestamps_block = resolve_timestamps_ref_to_timestamps_block(
            self.timestamps, self._default_timestamps
        )

        if (
            self.duration * 1e-3 * len(gids) * self.frequency * len(timestamps_block.timestamps())
            > _MAX_POISSON_SPIKE_LIMIT
        ):
            msg = (
                f"Poisson input exceeds maximum allowed nunmber of spikes "
                f"({_MAX_POISSON_SPIKE_LIMIT})!"
            )
            raise OBIONEError(msg)

        gid_spike_map = {}
        for timestamp_idx, timestamp_t in enumerate(timestamps_block.timestamps()):
            start_time = timestamp_t + self.timestamp_offset
            end_time = start_time + self.duration
            if (
                timestamp_idx < len(timestamps_block.timestamps()) - 1
                and not end_time < timestamps_block.timestamps()[timestamp_idx + 1]
            ):
                next_timestamp = timestamps_block.timestamps()[timestamp_idx + 1]
                stimulus_name_part = f" in '{self.block_name}'" if self.has_block_name() else ""
                msg = (
                    f"Stimulus time intervals overlap{stimulus_name_part}! "
                    f"Current stimulus ends at {end_time:.2f} ms "
                    f"(timestamp {timestamp_t:.2f} ms + offset {self.timestamp_offset:.2f} ms + "
                    f"duration {self.duration:.2f} ms), "
                    f"but next timestamp starts at {next_timestamp:.2f} ms. "
                    f"To fix: reduce 'duration', reduce 'timestamp_offset', "
                    f"or increase spacing between timestamps."
                )
                raise ValueError(msg)
            for gid in gids:
                spikes = []
                t = start_time
                while t < end_time:
                    # Draw next spike time from exponential distribution
                    interval = rng.exponential(1.0 / self.frequency) * 1000  # convert s → ms
                    t += interval
                    if t < end_time:
                        spikes.append(t)
                if gid in gid_spike_map:
                    gid_spike_map[gid] += spikes
                else:
                    gid_spike_map[gid] = spikes
        self._spike_file = f"{self.block_name}_spikes.h5"
        self.write_spike_file(
            gid_spike_map, spike_file_path / self._spike_file, source_node_population
        )

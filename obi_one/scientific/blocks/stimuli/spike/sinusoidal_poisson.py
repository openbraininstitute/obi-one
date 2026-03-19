from pathlib import Path
from typing import Annotated, ClassVar, Self

import numpy as np
from pydantic import (
    Field,
    NonNegativeFloat,
    PositiveFloat,
    model_validator,
)

from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_POISSON_SPIKE_LIMIT,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.unions.unions_timestamps import (
    resolve_timestamps_ref_to_timestamps_block,
)


def _draw_inhomogeneous_poisson_interval_ms(rng: np.random.Generator, lam_max_hz: float) -> float:
    """Draw a candidate inter-arrival time (ms) for a homogeneous process with rate lam_max."""
    if lam_max_hz <= 0.0:
        msg = "Maximum lambda must be positive to draw inter-arrival times."
        raise ValueError(msg)
    # Exponential with rate lam_max (in Hz) → seconds, then convert to ms
    return rng.exponential(1.0 / lam_max_hz) * 1000.0


class SinusoidalPoissonSpikeStimulus(SpikeStimulus):
    """Spike times drawn from an inhomogeneous Poisson process with sinusoidal rate.

    Sinusoid defined by a minimum and maximum rate.

    Sent from all neurons in the source neuron set to efferently connected
    neurons in the target neuron set.
    """

    title: ClassVar[str] = "Sinusoidal Poisson Spikes (Efferent)"

    _module: str = "synapse_replay"
    _input_type: str = "spikes"

    # --- timing ---
    duration: (
        Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration of the stimulus in milliseconds.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "ms",
        },
    )

    # --- sinusoidal rate params ---
    minimum_rate: (
        Annotated[PositiveFloat, Field(ge=0.00001, le=50.0)]
        | list[Annotated[PositiveFloat, Field(ge=0.00001, le=50.0)]]
    ) = Field(
        default=0.00001,
        title="Minimum Rate",
        description="Minimum rate of the stimulus in Hz.\n Must be less than the Maximum Rate.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "Hz",
        },
    )

    maximum_rate: (
        Annotated[PositiveFloat, Field(ge=0.00001, le=50.0)]
        | list[Annotated[PositiveFloat, Field(ge=0.00001, le=50.0)]]
    ) = Field(
        default=10.0,
        title="Maximum Rate",
        description="Maximum rate of the stimulus in Hz. Must be greater than or equal to "
        "Minimum Rate.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "Hz",
        },
    )

    modulation_frequency_hz: (
        Annotated[PositiveFloat, Field(ge=0.00001, le=100000.0)]
        | list[Annotated[PositiveFloat, Field(ge=0.00001, le=100000.0)]]
    ) = Field(
        default=5.0,
        title="Modulation Frequency",
        description="Frequency (Hz) of the sinusoidal modulation of the rate.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "Hz",
        },
    )

    phase_degrees: float | list[float] = Field(
        default=0.0,
        title="Phase Offset",
        description="Phase offset (degrees) of the sinusoid.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
            "units": "°",
        },
    )

    random_seed: int | list[int] = Field(
        default=0,
        title="Random Seed",
        description="Seed for the random number generator to ensure reproducibility.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )

    @model_validator(mode="after")
    def amplitude_greater_equal_baseline(self) -> Self:
        """Check if amplitude is greater than or equal to baseline for all epochs."""
        if isinstance(self.maximum_rate, list):
            amplitude_list = self.maximum_rate
        else:
            amplitude_list = [self.maximum_rate]
        if isinstance(self.minimum_rate, list):
            baseline_list = self.minimum_rate
        else:
            baseline_list = [self.minimum_rate]

        for min_r in baseline_list:
            for max_r in amplitude_list:
                if max_r < min_r:
                    msg = "Maximum rate must be greater than or equal to minimum rate."
                    raise ValueError(msg)

        return self

    # --- internal helpers ---
    @staticmethod
    def _lambda_t_ms(
        t_ms: float, minimum_rate: float, maximum_rate: float, mod_freq_hz: float, phase_rad: float
    ) -> float:
        """Instantaneous rate λ(t) at time t in ms, returned in Hz."""
        t_s = t_ms / 1000.0
        lam = minimum_rate + (maximum_rate - minimum_rate) * (
            (np.sin(2.0 * np.pi * mod_freq_hz * t_s + phase_rad) + 1.0) / 2.0
        )

        return max(0.0, lam)

    def generate_spikes(  # noqa: C901, PLR0914
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

        n_timestamps = len(timestamps_block.timestamps())

        # Upper-bound on expected spikes to guard against pathological params
        # Use the per-epoch maximum rate (baseline + amplitude, clipped >=0)
        total_expected = 0.0
        total_expected += (self.duration * n_timestamps / 1000.0) * self.maximum_rate * len(gids)
        if total_expected > _MAX_POISSON_SPIKE_LIMIT:
            msg = (
                f"Sinusoidal Poisson input exceeds maximum allowed number of spikes "
                f"({_MAX_POISSON_SPIKE_LIMIT})!"
            )
            raise ValueError(msg)

        gid_spike_map: dict[int, list[float]] = {}

        # Iterate epochs (non-overlapping enforced, like the original)
        for idx, t0 in enumerate(timestamps_block.timestamps()):
            start_time = t0 + self.timestamp_offset
            end_time = start_time + self.duration

            if idx < n_timestamps - 1 and not end_time < timestamps_block.timestamps()[idx + 1]:
                next_timestamp = timestamps_block.timestamps()[idx + 1]
                stimulus_name_part = f" in '{self.block_name}'" if self.has_block_name() else ""
                msg = (
                    f"Stimulus time intervals overlap{stimulus_name_part}! "
                    f"Current stimulus ends at {end_time:.2f} ms "
                    f"(timestamp {t0:.2f} ms + offset {self.timestamp_offset:.2f} ms + "
                    f"duration {self.duration:.2f} ms), "
                    f"but next timestamp starts at {next_timestamp:.2f} ms. "
                    f"To fix: reduce 'duration', reduce 'timestamp_offset', "
                    f"or increase spacing between timestamps."
                )
                raise ValueError(msg)

            # Thinning with epoch-specific λ_max
            lam_max_hz = self.maximum_rate

            for gid in gids:
                spikes = []
                t = start_time
                while t < end_time:
                    # 1) Draw candidate from homogeneous process with λ_max
                    dt_ms = _draw_inhomogeneous_poisson_interval_ms(rng, lam_max_hz)
                    if not np.isfinite(dt_ms):
                        break  # no spikes possible with current λ_max (i.e., λ_max==0)
                    t_candidate = t + dt_ms
                    if t_candidate >= end_time:
                        break

                    # 2) Accept with probability λ(t_candidate)/λ_max
                    lam_tc = self._lambda_t_ms(
                        t_candidate,
                        self.minimum_rate,
                        self.maximum_rate,
                        self.modulation_frequency_hz,
                        np.deg2rad(self.phase_degrees),
                    )
                    if lam_max_hz > 0.0:
                        accept_prob = lam_tc / lam_max_hz
                        if rng.uniform() <= accept_prob:
                            spikes.append(t_candidate)

                    # 3) Move time forward regardless of accept/reject
                    t = t_candidate

                if gid in gid_spike_map:
                    gid_spike_map[gid] += spikes
                else:
                    gid_spike_map[gid] = spikes

        self._spike_file = f"{self.block_name}_spikes.h5"
        self.write_spike_file(
            gid_spike_map, spike_file_path / self._spike_file, source_node_population
        )

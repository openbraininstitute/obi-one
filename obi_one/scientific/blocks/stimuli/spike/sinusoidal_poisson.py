from collections import defaultdict
from typing import Annotated, ClassVar, Self

import numpy as np
from pydantic import (
    Field,
    NonNegativeFloat,
    PositiveFloat,
    model_validator,
)

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_POISSON_SPIKE_LIMIT,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
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

    # --- timing ---
    duration: (
        Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration of the stimulus in milliseconds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
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
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
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
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
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
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )

    phase_degrees: float | list[float] = Field(
        default=0.0,
        title="Phase Offset",
        description="Phase offset (degrees) of the sinusoid.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.DEGREES,
        },
    )

    random_seed: int | list[int] = Field(
        default=0,
        title="Random Seed",
        description="Seed for the random number generator to ensure reproducibility.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
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

    def generate_spikes_by_gid(self, source_gids: list[int]) -> dict[int, list[float]]:
        rng = np.random.default_rng(self.random_seed)

        # Upper-bound on expected spikes to guard against pathological params
        total_expected = (
            (self.duration * len(self._offset_timestamps()) / 1000.0)  # ty:ignore[unsupported-operator]
            * self.maximum_rate
            * len(source_gids)
        )
        if total_expected > _MAX_POISSON_SPIKE_LIMIT:
            msg = (
                f"Sinusoidal Poisson input exceeds maximum allowed number of spikes "
                f"({_MAX_POISSON_SPIKE_LIMIT})!"
            )
            raise ValueError(msg)

        spikes_by_gid: dict[int, list[float]] = defaultdict(list)
        lam_max_hz = self.maximum_rate
        phase_rad = np.deg2rad(self.phase_degrees)

        for t0 in self._offset_timestamps():
            start_time = t0
            end_time = start_time + self.duration  # ty:ignore[unsupported-operator]

            for gid in source_gids:
                t = start_time
                while t < end_time:
                    dt_ms = _draw_inhomogeneous_poisson_interval_ms(rng, lam_max_hz)  # ty:ignore[invalid-argument-type]
                    if not np.isfinite(dt_ms):
                        break
                    t_candidate = t + dt_ms
                    if t_candidate >= end_time:
                        break

                    # Accept with probability λ(t_candidate)/λ_max
                    lam_tc = self._lambda_t_ms(
                        t_candidate - start_time,
                        self.minimum_rate,  # ty:ignore[invalid-argument-type]
                        self.maximum_rate,  # ty:ignore[invalid-argument-type]
                        self.modulation_frequency_hz,  # ty:ignore[invalid-argument-type]
                        phase_rad,  # ty:ignore[invalid-argument-type]
                    )
                    if lam_max_hz > 0.0 and rng.uniform() <= lam_tc / lam_max_hz:  # ty:ignore[unsupported-operator]
                        spikes_by_gid[gid].append(t_candidate)

                    t = t_candidate

        return spikes_by_gid

from collections import defaultdict
from typing import Annotated, ClassVar

import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_POISSON_SPIKE_LIMIT,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
    _MIN_NON_NEGATIVE_FLOAT_VALUE,
)


class PoissonSpikeStimulus(SpikeStimulus):
    """Spike times drawn from a Poisson process with a given frequency.

    Sent from all neurons in the source neuron set to efferently connected

    When using repeated resolved_timestamps (i.e. Regular Timestamps), stimulus durations
    should be small enough such that stimulus periods do not overlap across
    repetitions of the same stimulus.
    """

    title: ClassVar[str] = "Poisson Spikes (Efferent)"

    duration: (
        Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]
        | list[Annotated[NonNegativeFloat, Field(le=_MAX_SIMULATION_LENGTH_MILLISECONDS)]]
    ) = Field(
        default=_DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
        title="Duration",
        description="Time duration in milliseconds for how long input is activated.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
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
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.HERTZ,
        },
    )
    random_seed: int | list[int] = Field(
        default=0,
        title="Random Seed",
        description="Seed for the random number generator to ensure "
        "reproducibility of the spike generation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def generate_spikes_by_gid(self, source_gids: list[int]) -> dict[int, list[float]]:
        rng = np.random.default_rng(self.random_seed)

        if (
            self.duration
            * 1e-3  # ty:ignore[unsupported-operator]
            * len(source_gids)
            * self.frequency
            * len(self._offset_timestamps())
            > _MAX_POISSON_SPIKE_LIMIT
        ):
            msg = (
                f"Poisson input exceeds maximum allowed nunmber of spikes "
                f"({_MAX_POISSON_SPIKE_LIMIT})!"
            )
            raise OBIONEError(msg)

        spikes_by_gid: dict[int, list[float]] = defaultdict(list)
        for offset_timestamp in self._offset_timestamps():
            start_time = offset_timestamp
            end_time = start_time + self.duration  # ty:ignore[unsupported-operator]
            for gid in source_gids:
                t = start_time
                while t < end_time:
                    # Draw next spike time from exponential distribution
                    interval = (
                        rng.exponential(1.0 / self.frequency) * 1000  # ty:ignore[unsupported-operator]
                    )  # convert s → ms
                    t += interval
                    if t < end_time:
                        spikes_by_gid[gid].append(t)
        return spikes_by_gid

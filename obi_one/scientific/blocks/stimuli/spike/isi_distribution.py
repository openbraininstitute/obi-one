from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Annotated, ClassVar

import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units

if TYPE_CHECKING:
    from obi_one.scientific.blocks.distributions.base import Distribution
from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus
from obi_one.scientific.library.constants import (
    _DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    _MAX_SIMULATION_LENGTH_MILLISECONDS,
)
from obi_one.scientific.unions.unions_distributions import AllDistributionsReference


class InterSpikeIntervalDistributionSpikeStimulus(SpikeStimulus):
    """Spike replay generated from an inter-spike interval distribution."""

    title: ClassVar[str] = "Inter-Spike Interval Distribution Spike Replay (Efferent)"

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

    distribution: AllDistributionsReference | None = Field(
        default=None,
        title="Interval Distribution",
        description="Distribution used to sample inter-spike intervals in milliseconds.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
            SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
        },
    )

    resample_each_repetition: bool = Field(
        default=True,
        title="Resample Each Repetition",
        description=(
            "When set to True, the spike train is regenerated for every timestamp "
            "repetition. When False, the same relative spike pattern is reused for "
            "all repetitions."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
        },
    )

    @staticmethod
    def _generate_spike_train_from_distribution(
        distribution: Distribution,
        duration: float,
        rng: np.random.Generator | None = None,
    ) -> list[float]:
        spikes: list[float] = []
        t = 0.0
        while True:
            interval = distribution.sample(1, rng=rng)[0]
            if interval <= 0.0:
                msg = "Inter-spike intervals must be positive."
                raise ValueError(msg)
            t += interval
            if t >= duration:
                break
            spikes.append(t)
        return spikes

    def generate_spikes_by_gid(self, source_gids: list[int]) -> dict[int, list[float]]:
        if self.distribution is None:
            msg = "Distribution must be set for InterSpikeIntervalDistributionSpikeStimulus."
            raise ValueError(msg)

        timestamps = self._offset_timestamps()
        distribution = self.distribution.block
        random_seed = getattr(distribution, "random_seed", None)
        rng = np.random.default_rng(random_seed) if random_seed is not None else None

        spikes_by_gid: dict[int, list[float]] = defaultdict(list)

        for gid in source_gids:
            if self.resample_each_repetition:
                for timestamp in timestamps:
                    relative_spikes = self._generate_spike_train_from_distribution(
                        distribution,
                        self.duration,
                        rng=rng,
                    )
                    spike_offset = timestamp + self.timestamp_offset
                    spikes_by_gid[gid].extend(spike_offset + t for t in relative_spikes)
            else:
                relative_spikes = self._generate_spike_train_from_distribution(
                    distribution,
                    self.duration,
                    rng=rng,
                )
                for timestamp in timestamps:
                    spike_offset = timestamp + self.timestamp_offset
                    spikes_by_gid[gid].extend(spike_offset + t for t in relative_spikes)

        return spikes_by_gid

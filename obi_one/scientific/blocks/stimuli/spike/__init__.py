"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.stimuli.spike import (
    base,
    fully_synchronous,
    FullySynchronousSpikeStimulus,
    poisson,
    PoissonSpikeStimulus,
    sinusoidal_poisson,
    SinusoidalPoissonSpikeStimulus,
    SpikeStimulus,
)

__all__ = [
    "base",
    "fully_synchronous",
    "FullySynchronousSpikeStimulus",
    "poisson",
    "PoissonSpikeStimulus",
    "sinusoidal_poisson",
    "SinusoidalPoissonSpikeStimulus",
    "SpikeStimulus",
]

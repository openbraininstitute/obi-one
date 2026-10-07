"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.blocks.stimuli.spike.sinusoidal_poisson import (
    Annotated,
    ClassVar,
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    defaultdict,
    Field,
    MAX_POISSON_SPIKE_LIMIT,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    model_validator,
    NonNegativeFloat,
    np,
    PositiveFloat,
    SchemaKey,
    Self,
    SinusoidalPoissonSpikeStimulus,
    SpikeStimulus,
    UIElement,
    Units,
)

from obi_one_lazy.scientific.blocks.stimuli.spike.sinusoidal_poisson import (
    _draw_inhomogeneous_poisson_interval_ms,
)

__all__ = [
    "Annotated",
    "ClassVar",
    "DEFAULT_STIMULUS_LENGTH_MILLISECONDS",
    "defaultdict",
    "Field",
    "MAX_POISSON_SPIKE_LIMIT",
    "MAX_SIMULATION_LENGTH_MILLISECONDS",
    "model_validator",
    "NonNegativeFloat",
    "np",
    "PositiveFloat",
    "SchemaKey",
    "Self",
    "SinusoidalPoissonSpikeStimulus",
    "SpikeStimulus",
    "UIElement",
    "Units",
    "_draw_inhomogeneous_poisson_interval_ms",
]

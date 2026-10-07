"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.stimuli.spike.poisson import (
    Annotated,
    ClassVar,
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    defaultdict,
    Field,
    MAX_POISSON_SPIKE_LIMIT,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    MIN_NON_NEGATIVE_FLOAT_VALUE,
    NonNegativeFloat,
    np,
    OBIONEError,
    PoissonSpikeStimulus,
    SchemaKey,
    SpikeStimulus,
    UIElement,
    Units,
)

__all__ = [
    "Annotated",
    "ClassVar",
    "DEFAULT_STIMULUS_LENGTH_MILLISECONDS",
    "defaultdict",
    "Field",
    "MAX_POISSON_SPIKE_LIMIT",
    "MAX_SIMULATION_LENGTH_MILLISECONDS",
    "MIN_NON_NEGATIVE_FLOAT_VALUE",
    "NonNegativeFloat",
    "np",
    "OBIONEError",
    "PoissonSpikeStimulus",
    "SchemaKey",
    "SpikeStimulus",
    "UIElement",
    "Units",
]

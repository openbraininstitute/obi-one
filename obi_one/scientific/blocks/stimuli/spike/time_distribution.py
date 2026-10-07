"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.stimuli.spike.time_distribution import (
    AllDistributionsReference,
    Annotated,
    annotations,
    ClassVar,
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    defaultdict,
    Field,
    FloatUniformDistribution,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    NonNegativeFloat,
    np,
    SchemaKey,
    SpikeStimulus,
    SpikeTimeDistributionSpikeStimulus,
    TYPE_CHECKING,
    UIElement,
    Units,
)

__all__ = [
    "AllDistributionsReference",
    "Annotated",
    "annotations",
    "ClassVar",
    "DEFAULT_STIMULUS_LENGTH_MILLISECONDS",
    "defaultdict",
    "Field",
    "FloatUniformDistribution",
    "MAX_SIMULATION_LENGTH_MILLISECONDS",
    "NonNegativeFloat",
    "np",
    "SchemaKey",
    "SpikeStimulus",
    "SpikeTimeDistributionSpikeStimulus",
    "TYPE_CHECKING",
    "UIElement",
    "Units",
]

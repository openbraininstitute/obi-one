"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.stimuli.brian2_poisson import (
    Annotated,
    Block,
    Brian2DirectPoissonStimulus,
    ClassVar,
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    Field,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    NonNegativeFloat,
    POINT_NEURON_SETS_REFERENCE_TYPES,
    POINT_NEURON_SETS_REFERENCE_UNION,
    PrivateAttr,
    resolve_neuron_set_ref_to_node_set,
    SchemaKey,
    SingleTimestamp,
    TimestampsReference,
    UIElement,
    Units,
)

__all__ = [
    "Annotated",
    "Block",
    "Brian2DirectPoissonStimulus",
    "ClassVar",
    "DEFAULT_STIMULUS_LENGTH_MILLISECONDS",
    "Field",
    "MAX_SIMULATION_LENGTH_MILLISECONDS",
    "NonNegativeFloat",
    "POINT_NEURON_SETS_REFERENCE_TYPES",
    "POINT_NEURON_SETS_REFERENCE_UNION",
    "PrivateAttr",
    "resolve_neuron_set_ref_to_node_set",
    "SchemaKey",
    "SingleTimestamp",
    "TimestampsReference",
    "UIElement",
    "Units",
]

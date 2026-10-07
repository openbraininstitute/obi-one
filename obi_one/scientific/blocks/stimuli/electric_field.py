"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.blocks.stimuli.electric_field import (
    Annotated,
    CircuitUsability,
    ClassVar,
    ContinuousStimulus,
    DEFAULT_STIMULUS_LENGTH_MILLISECONDS,
    Field,
    MappedPropertiesGroup,
    MAX_EFIELD_FREQUENCY_HZ,
    MAX_SIMULATION_LENGTH_MILLISECONDS,
    model_validator,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    NonNegativeFloat,
    np,
    PrivateAttr,
    resolve_neuron_set_ref_to_node_set,
    SchemaKey,
    Self,
    SpatiallyUniformElectricFieldStimulus,
    TemporallyCosineSpatiallyUniformElectricFieldStimulus,
    UIElement,
    Units,
)

from obi_one_lazy.scientific.blocks.stimuli.electric_field import (
    _RAMP_QAULIFIER_DESCRIPTION,
)

__all__ = [
    "Annotated",
    "CircuitUsability",
    "ClassVar",
    "ContinuousStimulus",
    "DEFAULT_STIMULUS_LENGTH_MILLISECONDS",
    "Field",
    "MappedPropertiesGroup",
    "MAX_EFIELD_FREQUENCY_HZ",
    "MAX_SIMULATION_LENGTH_MILLISECONDS",
    "model_validator",
    "NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES",
    "NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION",
    "NonNegativeFloat",
    "np",
    "PrivateAttr",
    "resolve_neuron_set_ref_to_node_set",
    "SchemaKey",
    "Self",
    "SpatiallyUniformElectricFieldStimulus",
    "TemporallyCosineSpatiallyUniformElectricFieldStimulus",
    "UIElement",
    "Units",
    "_RAMP_QAULIFIER_DESCRIPTION",
]

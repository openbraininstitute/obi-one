"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    Annotated,
    BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    Block,
    ByNeuronMechanismVariableNeuronalManipulation,
    ByNeuronModification,
    BySectionListMechanismVariableNeuronalManipulation,
    BySectionListModification,
    CircuitByNeuronMechanismVariableNeuronalManipulation,
    CircuitBySectionListMechanismVariableNeuronalManipulation,
    CircuitMappedProperties,
    ClassVar,
    ComplexVariableHolder,
    Field,
    Literal,
    MappedPropertiesGroup,
    resolve_neuron_set_ref_to_node_set,
    SchemaKey,
    UIElement,
    uuid,
)

from obi_one_lazy.scientific.blocks.neuronal_manipulations.neuronal_manipulations import (
    _expand_section_list,
)

__all__ = [
    "Annotated",
    "BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES",
    "BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION",
    "Block",
    "ByNeuronMechanismVariableNeuronalManipulation",
    "ByNeuronModification",
    "BySectionListMechanismVariableNeuronalManipulation",
    "BySectionListModification",
    "CircuitByNeuronMechanismVariableNeuronalManipulation",
    "CircuitBySectionListMechanismVariableNeuronalManipulation",
    "CircuitMappedProperties",
    "ClassVar",
    "ComplexVariableHolder",
    "Field",
    "Literal",
    "MappedPropertiesGroup",
    "resolve_neuron_set_ref_to_node_set",
    "SchemaKey",
    "UIElement",
    "uuid",
    "_expand_section_list",
]

"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.blocks.synaptic_manipulations.base import (
    ABC,
    ALL_NEURON_SETS_REFERENCE_TYPES,
    ALL_NEURON_SETS_REFERENCE_UNION,
    Block,
    DelayedInterNeuronSetSynapticManipulation,
    Field,
    GlobalVariableInterNeuronSetSynapticManipulation,
    InterNeuronSetSynapticManipulation,
    ModSpecificVariableInterNeuronSetSynapticManipulation,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES,
    NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION,
    PrivateAttr,
    resolve_neuron_set_ref_to_node_set,
    resolve_timestamps_ref_to_timestamps_block,
    SchemaKey,
    SingleTimestamp,
    TimestampsReference,
    UIElement,
    Units,
    WeightChangeDelayedInterNeuronSetSynapticManipulation,
)

from obi_one_lazy.scientific.blocks.synaptic_manipulations.base import (
    _NEURON_SET_DESCRIPTION,
)

__all__ = [
    "ABC",
    "ALL_NEURON_SETS_REFERENCE_TYPES",
    "ALL_NEURON_SETS_REFERENCE_UNION",
    "Block",
    "DelayedInterNeuronSetSynapticManipulation",
    "Field",
    "GlobalVariableInterNeuronSetSynapticManipulation",
    "InterNeuronSetSynapticManipulation",
    "ModSpecificVariableInterNeuronSetSynapticManipulation",
    "NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES",
    "NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION",
    "PrivateAttr",
    "resolve_neuron_set_ref_to_node_set",
    "resolve_timestamps_ref_to_timestamps_block",
    "SchemaKey",
    "SingleTimestamp",
    "TimestampsReference",
    "UIElement",
    "Units",
    "WeightChangeDelayedInterNeuronSetSynapticManipulation",
    "_NEURON_SET_DESCRIPTION",
]

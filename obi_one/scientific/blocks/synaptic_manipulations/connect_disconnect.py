"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.synaptic_manipulations.connect_disconnect import (
    ClassVar,
    ConnectSynapticManipulation,
    DisconnectSynapticManipulation,
    PrivateAttr,
    WeightChangeDelayedInterNeuronSetSynapticManipulation,
)

__all__ = [
    "ClassVar",
    "ConnectSynapticManipulation",
    "DisconnectSynapticManipulation",
    "PrivateAttr",
    "WeightChangeDelayedInterNeuronSetSynapticManipulation",
]

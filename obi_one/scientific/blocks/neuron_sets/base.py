"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.blocks.neuron_sets.base import (
    abc,
    add_node_set_to_circuit,
    Block,
    Circuit,
    ClassVar,
    json,
    L,
    logging,
    NeuronSet,
    NeuronSetPopulationType,
    os,
    Path,
    snap,
    SonataPopulationType,
    StrEnum,
    TYPES_OF_BIOPHYS_NODES,
    TYPES_OF_POINT_NODES,
    TYPES_OF_VIRTUAL_NODES,
)

__all__ = [
    "abc",
    "add_node_set_to_circuit",
    "Block",
    "Circuit",
    "ClassVar",
    "json",
    "L",
    "logging",
    "NeuronSet",
    "NeuronSetPopulationType",
    "os",
    "Path",
    "snap",
    "SonataPopulationType",
    "StrEnum",
    "TYPES_OF_BIOPHYS_NODES",
    "TYPES_OF_POINT_NODES",
    "TYPES_OF_VIRTUAL_NODES",
]

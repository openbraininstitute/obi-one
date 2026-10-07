"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.unions_and_references.manipulations import (
    Annotated,
    Any,
    BlockReference,
    Brian2SynapticManipulationsUnion,
    ClassVar,
    ConnectSynapticManipulation,
    DisconnectSynapticManipulation,
    Discriminator,
    ScaleAcetylcholineUSESynapticManipulation,
    SynapticManipulationsReference,
    SynapticManipulationsUnion,
    SynapticMgManipulation,
)

from obi_one_lazy.scientific.unions_and_references.manipulations import (
    _BRIAN2_SYNAPTIC_MANIPULATIONS,
    _SYNAPTIC_MANIPULATIONS,
)

__all__ = [
    "Annotated",
    "Any",
    "BlockReference",
    "Brian2SynapticManipulationsUnion",
    "ClassVar",
    "ConnectSynapticManipulation",
    "DisconnectSynapticManipulation",
    "Discriminator",
    "ScaleAcetylcholineUSESynapticManipulation",
    "SynapticManipulationsReference",
    "SynapticManipulationsUnion",
    "SynapticMgManipulation",
    "_BRIAN2_SYNAPTIC_MANIPULATIONS",
    "_SYNAPTIC_MANIPULATIONS",
]

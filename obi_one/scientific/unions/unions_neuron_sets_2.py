from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets_2.id import (
    BiophysicalIDNeuronSet,
    PointIDNeuronSet,
    VirtualIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets_2.property import (
    BiophysicalPropertyNeuronSet,
    VirtualPropertyNeuronSet,
    PointPropertyNeuronSet,
)

_BIOPHYSICAL_NEURON_SETS = BiophysicalIDNeuronSet | BiophysicalPropertyNeuronSet
_VIRTUAL_NEURON_SETS = VirtualIDNeuronSet | VirtualPropertyNeuronSet
_POINT_NEURON_SETS = PointIDNeuronSet | PointPropertyNeuronSet
_ALL_NEURON_SETS = _BIOPHYSICAL_NEURON_SETS | _VIRTUAL_NEURON_SETS | _POINT_NEURON_SETS
_BIOPHYSICAL_AND_POINT_NEURON_SETS = _BIOPHYSICAL_NEURON_SETS | _POINT_NEURON_SETS


BiophysicalNeuronSetUnion = Annotated[
    _BIOPHYSICAL_NEURON_SETS,
    Discriminator("type"),
]

VirtualNeuronSetUnion = Annotated[
    _VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

PointNeuronSetUnion = Annotated[
    _POINT_NEURON_SETS,
    Discriminator("type"),
]

AllNeuronSetUnion = Annotated[
    _ALL_NEURON_SETS,
    Discriminator("type"),
]

NonVirtualNeuronSetUnion = Annotated[
    _BIOPHYSICAL_AND_POINT_NEURON_SETS,
    Discriminator("type"),
]


class BiophysicalNeuronSetReference(BlockReference):
    """A reference to a Biophysical or Point NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = BiophysicalNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_BIOPHYSICAL_NEURON_SETS)
    }


class VirtualNeuronSetReference(BlockReference):
    """A reference to a Virtual NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = VirtualNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_VIRTUAL_NEURON_SETS)
    }


class PointNeuronSetReference(BlockReference):
    """A reference to a Point NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = PointNeuronSetUnion

    json_schema_extra_additions: ClassVar[dict] = {
        "allowed_block_types": BlockReference.get_class_names(_POINT_NEURON_SETS)
    }


ALL_NEURON_SETS_REFERENCE_UNION = (
    BiophysicalNeuronSetReference | VirtualNeuronSetReference | PointNeuronSetReference
)
NON_VIRTUAL_NEURON_SETS_REFERENCE_UNION = BiophysicalNeuronSetReference | PointNeuronSetReference

ALL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
    VirtualNeuronSetReference.__name__,
    PointNeuronSetReference.__name__,
]
NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
    PointNeuronSetReference.__name__,
]


def resolve_neuron_set_2_ref_to_node_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None, default_node_set: str
) -> str:
    if neuron_set_reference is None:
        return default_node_set

    return neuron_set_reference.block.block_name


def resolve_neuron_set_2_ref_to_neuron_set(
    neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
    default_neuron_set_reference: ALL_NEURON_SETS_REFERENCE_UNION | None,
) -> AllNeuronSetUnion | None:
    if neuron_set_reference is None:
        if default_neuron_set_reference is None:
            msg = (
                "NeuronSet2Reference is None and no default_neuron_set provided. "
                "Cannot resolve to a NeuronSet2."
            )
            raise ValueError(msg)

        return default_neuron_set_reference.block

    return neuron_set_reference.block

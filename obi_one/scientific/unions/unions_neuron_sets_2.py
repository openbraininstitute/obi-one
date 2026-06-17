from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets_2.combined import (
    BiophysicalCombinedNeuronSet,
    CombinedNeuronSet,
    PointCombinedNeuronSet,
    VirtualCombinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets_2.id import (
    BiophysicalPopulationIDNeuronSet,
    PointPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets_2.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets_2.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
    PointPopulationPredefinedNeuronSet,
    PredefinedNeuronSet,
    VirtualPopulationPredefinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets_2.property import (
    BiophysicalPopulationPropertyNeuronSet,
    PointPopulationPropertyNeuronSet,
    VirtualPopulationPropertyNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets_2.specific import (
    AllBiophysicalNeurons,
    AllNeurons,
    AllPointNeurons,
    AllVirtualNeurons,
)

_BIOPHYSICAL_NEURON_SETS = (
    BiophysicalPopulationNeuronSet
    | BiophysicalPopulationIDNeuronSet
    | BiophysicalPopulationPropertyNeuronSet
    | BiophysicalPopulationPredefinedNeuronSet
    | BiophysicalCombinedNeuronSet
    | AllBiophysicalNeurons
)
_VIRTUAL_NEURON_SETS = (
    VirtualPopulationNeuronSet
    | VirtualPopulationIDNeuronSet
    | VirtualPopulationPropertyNeuronSet
    | VirtualPopulationPredefinedNeuronSet
    | VirtualCombinedNeuronSet
    | AllVirtualNeurons
)
_POINT_NEURON_SETS = (
    PointPopulationNeuronSet
    | PointPopulationIDNeuronSet
    | PointPopulationPropertyNeuronSet
    | PointPopulationPredefinedNeuronSet
    | PointCombinedNeuronSet
    | AllPointNeurons
)
_NONVIRTUAL_NEURON_SETS = _BIOPHYSICAL_NEURON_SETS | _POINT_NEURON_SETS
_ALL_NEURON_SETS = (
    _BIOPHYSICAL_NEURON_SETS
    | _VIRTUAL_NEURON_SETS
    | _POINT_NEURON_SETS
    | _NONVIRTUAL_NEURON_SETS
    | PredefinedNeuronSet
    | CombinedNeuronSet
    | AllNeurons
)


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
    _NONVIRTUAL_NEURON_SETS,
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
BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION = BiophysicalNeuronSetReference
VIRTUAL_NEURON_SETS_REFERENCE_UNION = VirtualNeuronSetReference
POINT_NEURON_SETS_REFERENCE_UNION = PointNeuronSetReference

ALL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
    VirtualNeuronSetReference.__name__,
    PointNeuronSetReference.__name__,
]
NON_VIRTUAL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
    PointNeuronSetReference.__name__,
]
BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES = [
    BiophysicalNeuronSetReference.__name__,
]
VIRTUAL_NEURON_SETS_REFERENCE_TYPES = [
    VirtualNeuronSetReference.__name__,
]
POINT_NEURON_SETS_REFERENCE_TYPES = [
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

        return default_neuron_set_reference.block  # ty:ignore[invalid-return-type]

    return neuron_set_reference.block  # ty:ignore[invalid-return-type]

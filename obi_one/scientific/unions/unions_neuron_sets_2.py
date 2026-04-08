from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets_2.id import (
    BiophysicalIDNeuronSet,
    PointIDNeuronSet,
    VirtualIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets_2.population import (
    BiophysicalPopulationNeuronSet,
    PointPopulationNeuronSet,
    VirtualPopulationNeuronSet,
)

_BIOPHYSICAL_NEURON_SETS = BiophysicalIDNeuronSet | BiophysicalPopulationNeuronSet
_VIRTUAL_NEURON_SETS = VirtualIDNeuronSet | VirtualPopulationNeuronSet
_POINT_NEURON_SETS = PointIDNeuronSet | PointPopulationNeuronSet
_ALL_NEURON_SETS = _BIOPHYSICAL_NEURON_SETS | _VIRTUAL_NEURON_SETS | _POINT_NEURON_SETS
_BIOPHYSICAL_AND_POINT_NEURON_SETS = _BIOPHYSICAL_NEURON_SETS | _POINT_NEURON_SETS

VirtualNeuronSet2Union = Annotated[
    _VIRTUAL_NEURON_SETS,
    Discriminator("type"),
]

PointNeuronSet2Union = Annotated[
    _POINT_NEURON_SETS,
    Discriminator("type"),
]

AllNeuronSet2Union = Annotated[
    _ALL_NEURON_SETS,
    Discriminator("type"),
]

BiophysicalAndPointNeuronSet2Union = Annotated[
    _BIOPHYSICAL_AND_POINT_NEURON_SETS,
    Discriminator("type"),
]


class NeuronSet2Reference(BlockReference):
    """A reference to a NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = AllNeuronSet2Union


class BiophysicalAndPointNeuronSet2Reference(BlockReference):
    """A reference to a Biophysical or Point NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = BiophysicalAndPointNeuronSet2Union

class VirtualNeuronSet2Reference(BlockReference):
    """A reference to a Virtual NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = VirtualNeuronSet2Union


def resolve_neuron_set_2_ref_to_node_set(
    neuron_set_reference: NeuronSet2Reference | None, default_node_set: str
) -> str:
    if neuron_set_reference is None:
        return default_node_set

    return neuron_set_reference.block.block_name


def resolve_neuron_set_2_ref_to_neuron_set(
    neuron_set_reference: NeuronSet2Reference | None,
    default_neuron_set_reference: NeuronSet2Reference | None,
) -> AllNeuronSet2Union | None:
    if neuron_set_reference is None:
        if default_neuron_set_reference is None:
            msg = (
                "NeuronSet2Reference is None and no default_neuron_set provided. "
                "Cannot resolve to a NeuronSet2."
            )
            raise ValueError(msg)

        return default_neuron_set_reference.block

    return neuron_set_reference.block
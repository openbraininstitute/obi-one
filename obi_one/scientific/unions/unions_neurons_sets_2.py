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

_POPULATION_NEURON_SETS = (
    BiophysicalPopulationNeuronSet | VirtualPopulationNeuronSet | PointPopulationNeuronSet
)
_ID_NEURON_SETS = BiophysicalIDNeuronSet | VirtualIDNeuronSet | PointIDNeuronSet

NeuronSet2Union = Annotated[
    _BIOPHYSICAL_NEURON_SETS | _VIRTUAL_NEURON_SETS | _POINT_NEURON_SETS,
    Discriminator("type"),
]


class NeuronSet2Reference(BlockReference):
    """A reference to a NeuronSet2 block."""

    allowed_block_types: ClassVar[Any] = NeuronSet2Union


def resolve_neuron_set_2_ref_to_node_set(
    neuron_set_reference: NeuronSet2Reference | None, default_node_set: str
) -> str:
    if neuron_set_reference is None:
        return default_node_set

    return neuron_set_reference.block.block_name

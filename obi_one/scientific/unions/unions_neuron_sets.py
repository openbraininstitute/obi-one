from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets.combined import CombinedNeuronSet
from obi_one.scientific.blocks.neuron_sets.id import IDNeuronSet
from obi_one.scientific.blocks.neuron_sets.pair import PairMotifNeuronSet
from obi_one.scientific.blocks.neuron_sets.predefined import PredefinedNeuronSet
from obi_one.scientific.blocks.neuron_sets.property import PropertyNeuronSet
from obi_one.scientific.blocks.neuron_sets.simplex import (
    SimplexMembershipBasedNeuronSet,
    SimplexNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllNeurons,
    ExcitatoryNeurons,
    InhibitoryNeurons,
    nbS1POmInputs,
    nbS1VPMInputs,
    rCA1CA3Inputs,
)
from obi_one.scientific.blocks.neuron_sets.volumetric import (
    VolumetricCountNeuronSet,
    VolumetricRadiusNeuronSet,
)

NeuronSetUnion = Annotated[
    CombinedNeuronSet
    | IDNeuronSet
    | PredefinedNeuronSet
    | PropertyNeuronSet
    | PairMotifNeuronSet
    | VolumetricCountNeuronSet
    | VolumetricRadiusNeuronSet
    | SimplexNeuronSet
    | SimplexMembershipBasedNeuronSet
    | nbS1VPMInputs
    | nbS1POmInputs
    | rCA1CA3Inputs
    | AllNeurons
    | ExcitatoryNeurons
    | InhibitoryNeurons,
    Discriminator("type"),
]


SimulationNeuronSetUnion = Annotated[
    IDNeuronSet
    | AllNeurons
    | ExcitatoryNeurons
    | InhibitoryNeurons
    | PredefinedNeuronSet
    | nbS1VPMInputs
    | nbS1POmInputs,
    Discriminator("type"),
]


class NeuronSetReference(BlockReference):
    """A reference to a NeuronSet block."""

    allowed_block_types: ClassVar[Any] = NeuronSetUnion


def resolve_neuron_set_ref_to_node_set(
    neuron_set_reference: NeuronSetReference | None, default_node_set: str
) -> str:
    if neuron_set_reference is None:
        return default_node_set

    return neuron_set_reference.block.block_name

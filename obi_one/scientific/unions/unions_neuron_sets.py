from typing import Annotated, Any, ClassVar

from pydantic import Discriminator

from obi_one.core.block_reference import BlockReference
from obi_one.scientific.blocks.neuron_sets import (
    AllNeurons,
    CombinedNeuronSet,
    ExcitatoryNeurons,
    IDNeuronSet,
    InhibitoryNeurons,
    PredefinedNeuronSet,
    PropertyNeuronSet,
    SimplexMembershipBasedNeuronSet,
    SimplexNeuronSet,
    VolumetricCountNeuronSet,
    VolumetricRadiusNeuronSet,
    nbS1POmInputs,
    nbS1VPMInputs,
    rCA1CA3Inputs,
)

NeuronSetUnion = Annotated[
    CombinedNeuronSet
    | IDNeuronSet
    | PredefinedNeuronSet
    | PropertyNeuronSet
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
    | nbS1VPMInputs
    | nbS1POmInputs
    | AllNeurons
    | ExcitatoryNeurons
    | InhibitoryNeurons
    | PredefinedNeuronSet,
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

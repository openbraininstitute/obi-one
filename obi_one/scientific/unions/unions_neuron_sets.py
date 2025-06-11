from obi_one.scientific.circuit.neuron_sets import (
    CombinedNeuronSet,
    IDNeuronSet,
    PredefinedNeuronSet,
    PropertyNeuronSet,
    VolumetricCountNeuronSet,
    VolumetricRadiusNeuronSet,
)

NeuronSetUnion = (
    PredefinedNeuronSet
    | CombinedNeuronSet
    | IDNeuronSet
    | PropertyNeuronSet
    | VolumetricCountNeuronSet
    | VolumetricRadiusNeuronSet
)

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class NeuronSetBlockReference(BlockReference):
    """A reference to a NeuronSet block."""
    
    allowed_block_types: ClassVar[Any] = NeuronSetUnion

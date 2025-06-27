from obi_one.scientific.circuit.neuron_sets import (
    CombinedNeuronSet,
    IDNeuronSet,
    PredefinedNeuronSet,
    PropertyNeuronSet,
    VolumetricCountNeuronSet,
    VolumetricRadiusNeuronSet,
    SimplexNeuronSet,
    SimplexMembershipBasedNeuronSet,
    nbS1VPMInputs,
    nbS1POmInputs,
    rCA1CA3Inputs,
    AllNeurons,
    ExcitatoryNeurons,
    InhibitoryNeurons,
)

NeuronSetUnion = (
    PredefinedNeuronSet
    | CombinedNeuronSet
    | IDNeuronSet
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
    | InhibitoryNeurons
)

SimulationNeuronSetUnion = (
    AllNeurons
    | ExcitatoryNeurons
    | InhibitoryNeurons
    | IDNeuronSet
    | nbS1VPMInputs
    | nbS1POmInputs
    | rCA1CA3Inputs
)

from obi_one.core.block_reference import BlockReference
from typing import ClassVar, Any
class NeuronSetReference(BlockReference):
    """A reference to a NeuronSet block."""
    
    allowed_block_types: ClassVar[Any] = NeuronSetUnion


# class SimulationNeuronSetReference(BlockReference):
#     """A reference to a NeuronSet block for simulation."""
    
#     allowed_block_types: ClassVar[Any] = SimulationNeuronSetUnion
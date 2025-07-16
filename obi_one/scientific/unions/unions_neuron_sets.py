from obi_one.scientific.circuit.neuron_sets import (
    AllNeurons,
    CombinedNeuronSet,
    ExcitatoryNeurons,
    IDNeuronSet,
    InhibitoryNeurons,
    PairMotifNeuronSet,
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

NeuronSetUnion = (
    PredefinedNeuronSet
    | CombinedNeuronSet
    | IDNeuronSet
    | PairMotifNeuronSet
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
    AllNeurons | ExcitatoryNeurons | InhibitoryNeurons | IDNeuronSet | nbS1VPMInputs | nbS1POmInputs
)

from typing import Any, ClassVar

from obi_one.core.block_reference import BlockReference


class NeuronSetReference(BlockReference):
    """A reference to a NeuronSet block."""

    allowed_block_types: ClassVar[Any] = NeuronSetUnion


# class SimulationNeuronSetReference(BlockReference):
#     """A reference to a NeuronSet block for simulation."""

#     allowed_block_types: ClassVar[Any] = SimulationNeuronSetUnion

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

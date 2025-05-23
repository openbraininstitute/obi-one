from obi_one.scientific.circuit.neuron_sets import (
    CombinedNeuronSet,
    IDNeuronSet,
    PredefinedNeuronSet,
    PropertyNeuronSet,
    VolumetricRadiusNeuronSet,
    VolumetricCountNeuronSet
)

NeuronSetUnion = PredefinedNeuronSet | CombinedNeuronSet | IDNeuronSet | PropertyNeuronSet | VolumetricCountNeuronSet | VolumetricRadiusNeuronSet

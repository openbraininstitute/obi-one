from obi_one.scientific.circuit.neuron_sets import (
    CombinedNeuronSet,
    IDNeuronSet,
    PredefinedNeuronSet,
    PropertyNeuronSet,
)

NeuronSetUnion = PredefinedNeuronSet | CombinedNeuronSet | IDNeuronSet | PropertyNeuronSet

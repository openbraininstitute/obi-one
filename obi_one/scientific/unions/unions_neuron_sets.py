from obi_one.scientific.circuit.neuron_sets import (
    CombinedNeuronSet,
    IDNeuronSet,
    PredefinedNeuronSet,
    PropertyNeuronSet,
)
from obi_one.scientific.circuit_parameterized_neuron_sets.volumetric_neuron_set_block import (
    VolumetricNeuronSetBlock
)

NeuronSetUnion = PredefinedNeuronSet | CombinedNeuronSet | IDNeuronSet | PropertyNeuronSet | VolumetricNeuronSetBlock

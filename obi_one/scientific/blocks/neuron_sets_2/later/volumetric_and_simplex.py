"""Volumetric/Simplex…NeuronSet(PopulationNeuronSet) [NEW - redefined].

- initial_neuron_set (optional): PopulationNeuronSet | None

- Volumetric/simplex extraction among the neurons provided as initial neuron set (or whole node
    population if not provided)
- Since here the order is important (both computationally and w.r.t. the results), it is not
    possible to combine afterwards
- The initial neuron set's node population must be the same as the actual node population, i.e.,
     if the initial neuron set is provided, the actual node population can be pre-filled
- IMPORTANT: When resolving a Volumetric/Simplex…NeuronSet, recursive infinite loops may occur
    (if initial_neuron_set is provided) and should be detected/avoided!
- Replaces: Old Volumetric/Simplex…NeuronSet but which now requires a combined property/predefine
    neuron set as initial neuron set
"""

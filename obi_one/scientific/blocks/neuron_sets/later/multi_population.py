"""MultiPopulationNeuronSet(NeuronSet) [NEW].

- population_neuron_sets: list[PopulationNeuronSet]


- Will combine a list of population neuron sets in a union
- Supports neurons sets of different node populations, i.e., the resulting neuron set can span
    multiple node populations
- No sampling possible (BUT: sampling can be used in each individual population neuron
    set in the list)
- May be restricted to either non-virtual or virtual populations only, i.e., not mixing
    virtual and non-virtual types (?) à To be discussed
- Example use cases:
    - Combining multiple biophysical populations to be used as simulation target
    - Combining multiple virtual populations as stimulus source
"""

"""CombinedNeuronSet(PopulationNeuronSet) [NEW - redefined].

- base_neuron_set: PopulationNeuronSet
- combined_with: list[tuple[[PopulationNeuronSet, Operation]]


- Will combine different neuron sets belonging to the same node population
- Will apply a series of set operations to the base_neuron_set
- Combinations are applied in sequential order as provided in the combined_with list:
res = base_neuron_set
for nset, op in combined_with:
    res = op(res, nset)
i.e., (((N0 op1 N1) op2 N2) op3 N3)… where N0 is the base_neuron_set

- The base_neuron_set must always exist
- The combined_with list may be empty, in which case no operations are applied
- Possible set operations: union, intersect, diff
- IMPORTANT: All neuron sets in combined_with must have the same node_population as the
    base_neuron_set (to avoid multi-population neuron sets!)
- IMPORTANT: When resolving a CombinedNeuronSet, recursive infinite loops may occur and
    should be detected/avoided!
- Replaces: node_sets functionality of the old PropertyNeuronSet, i.e., one can now create a
    combined neurons set based on a PropertyNeuronSet and PredefinedNeuronSet(s) to have
        the same behavior as before.
"""

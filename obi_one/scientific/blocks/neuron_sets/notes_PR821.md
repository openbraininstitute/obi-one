# Notes and remaining issues from PR#821

Link: https://github.com/openbraininstitute/obi-one/pull/821


## Add other types of point neurons

There are two other types of point neuron we now support

See [here](https://github.com/openbraininstitute/obi-one/blob/7cab6f0f3cad3a7fdf9412300f59f555e3c782ec/obi_one/scientific/library/circuit_metrics.py#L33)

```
TYPES_OF_POINT_NODES = ["point_process", "point_neuron", "brian2_point", "inait_point_neuron_lif"]
```

I think we'll need to update this statement. Also Circuit.get_node_population_names will need to be updated with this also. Are there other places too? Perhaps we can use a single list of constants across these different places

Will handle this in a separate PR, since we need to rebase to main to have TYPES_OF_POINT_NODES available.


## Solve circular import problem in CombinedNeuronSets

I see. Yes, let's find a solution later. Just to make a note for later, two other possible solutions might be to:

- Create a union within this class, which includes the class itself. Not sure if that's possible
- We can't use CombinedNeuronSets within a CombinedNeuronSet - Hopefully we can avoid this


## Proper use of general PredefinedNeuronSet and CombinedNeuronSet

Only allowing the PredefinedNeuronSet and CombinedNeuronSet to be used as the source of spike replay

Yes, this makes sense. But I am not even sure we should support spike replay from multiple populations within one stimulus block? Currently, it uses ALL_NEURON_SETS_REFERENCE_UNION which does not include the general CombinedNeuronSet and PredefinedNeuronSet types, but we can add them later of course.


## Add missing neuron sets to unions

I noticed that there are two neuron sets which are defined and potentially useful but not in unions_neuron_set2.py, namely:

- NonVirtualCombinedNeuronSet - Useful as the target of the simulation, and potentially as the target of non virtual supporting stimuli + recordings? Related to your comment below: "not even sure we should support spike replay support spike replay from multiple populations within one stimulus block", but I think we can deal with this when we integrate with the simulation generation task?
- AllNonVirtualNeurons - Also seems useful as the default target of the simulation?


## NonVirtualPredefinedNeuronSet

I agree. I think we can come back to NonVirtualPredefinedNeuronSet in the future if we need it, and consider which neuron sets are supported by the different stimuli when we integrate with the generate_simulations task
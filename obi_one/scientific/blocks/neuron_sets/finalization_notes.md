# Finalization notes

Christoph:
- Tests
- Fix example notebooks that use neuron sets

James:
- Check brian2 & learning engine
- Think about circular imports in combine neuron sets

Done:
- Add new classes to __init__.py
- Review adding_point_population_types
- Merge adding_point_population_types
- Linting/type checking (including raising error for spike replay, multi populations)

Old remaining questions (maybe we already decided):
- Do we still need:
-- NonVirtualCombinedNeuronSet - Useful as the target of the simulation, and potentially as the target of non virtual supporting stimuli + recordings? Related to your comment below: "not even sure we should support spike replay support spike replay from multiple populations within one stimulus block", but I think we can deal with this when we integrate with the simulation generation task?
-- AllNonVirtualNeurons - Also seems useful as the default target of the simulation?


Later (before initial deployment):
- Check brian2 & learning engine

After initial deployment:
- Resolve circular imports issue with combined neuron sets
- Merge combined_neuron_sets

Choices for now:
- 2 neuron sets with Any population types —> Commented out
- Remove non-virtual variables from unions



# Misc notes:

## Notes and remaining issues from PR#821

Link: https://github.com/openbraininstitute/obi-one/pull/821


## Circular imports

- Create a union within this class, which includes the class itself. Not sure if that's possible
- We can't use CombinedNeuronSets within a CombinedNeuronSet - Hopefully we can avoid this
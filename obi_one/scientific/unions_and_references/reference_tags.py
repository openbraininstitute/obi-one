"""Roles a block reference field can play, used to say what an unset reference means.

Every block reference field that may be left unset carries one of these under
``SchemaKey.REFERENCE_TAG`` in its ``json_schema_extra``. A task then maps each tag to the block
reference to substitute, and one pass over the config fills every ``None`` in one place -- see
``obi_one.core.fill_none_references``.

The tag names the *role*, not the field, so two fields that mean the same thing share a tag and a
task that wants them to differ can still tell them apart. ``stimulus_target`` is the clearest
example: a NEURON simulation resolves it to the simulation-wide default neuron set, while a Brian2
simulation resolves it to the much smaller ``sugar`` node set.
"""

from enum import StrEnum


class ReferenceTag(StrEnum):
    """The role a block reference field plays within a task."""

    # Neuron sets
    SIMULATION_TARGET = "simulation_target"
    STIMULUS_TARGET = "stimulus_target"
    SPIKE_REPLAY_SOURCE = "spike_replay_source"
    SPIKE_REPLAY_TARGET = "spike_replay_target"
    RECORDING_TARGET = "recording_target"
    SYNAPTIC_MANIPULATION_SOURCE = "synaptic_manipulation_source"
    SYNAPTIC_MANIPULATION_TARGET = "synaptic_manipulation_target"
    NEURONAL_MANIPULATION_TARGET = "neuronal_manipulation_target"
    MORPHOLOGY_LOCATIONS_TARGET = "morphology_locations_target"

    # Operands of a combined neuron set. There is one tag per population type because each
    # combined subclass redeclares base_neuron_set and combined_with with its own reference
    # union, and an unset operand means "every neuron of the combined set's own type".
    ANY_NEURON_SET_OPERAND = "any_neuron_set_operand"
    BIOPHYSICAL_NEURON_SET_OPERAND = "biophysical_neuron_set_operand"
    POINT_NEURON_SET_OPERAND = "point_neuron_set_operand"
    VIRTUAL_NEURON_SET_OPERAND = "virtual_neuron_set_operand"
    NON_VIRTUAL_NEURON_SET_OPERAND = "non_virtual_neuron_set_operand"

    # Timestamps. Stimuli and delayed synaptic manipulations share this: both mean "the times at
    # which this block acts", and both start at the beginning of the simulation when unset.
    TIMESTAMPS = "timestamps"

    # Distributions. These two are kept apart because their defaults differ in kind, and both are
    # currently supplied by the block itself rather than by the task -- the spike time default
    # spans the stimulus's own duration, which no task-level reference can express.
    INTER_SPIKE_INTERVAL_DISTRIBUTION = "inter_spike_interval_distribution"
    SPIKE_TIME_DISTRIBUTION = "spike_time_distribution"

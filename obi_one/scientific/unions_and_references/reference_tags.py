"""Roles a block reference field can play, used to say what an unset reference means.

A block reference field that may be left unset carries one of these under
``SchemaKey.REFERENCE_TAG`` in its ``json_schema_extra``, and the ScanConfig holding it answers
per role under ``SchemaKey.REFERENCE_TAG_DEFAULTS``. The UI shows that answer as the field's
default option.

The tag names the *role*, not the field, so fields that mean the same thing share a tag and an
answer. That is what ``DEFAULT_BLOCK_REFERENCE_LABELS`` cannot express: it is keyed by reference
type, so every field accepting ``AllDistributionsReference`` is forced to show the same text -
which for the Tsodyks-Markram parameters means nine fields with nine different built-in defaults
all reading alike.

Every reference field reachable from a config that declares these should carry one, so that no
field is left showing a type-keyed label that says the same thing as eight others.
"""

from enum import StrEnum


class ReferenceTag(StrEnum):
    """The role a block reference field plays within a task."""

    # Tsodyks-Markram parameter distributions. One per parameter rather than one for all of
    # them: each falls back to a different built-in distribution, so each needs its own answer.
    # Excitatory and inhibitory synapses take different values for the same parameter, so
    # each concrete model answers its own roles rather than sharing one set with the other.
    EXCITATORY_U_HILL_COEFFICIENT_DISTRIBUTION = "excitatory_u_hill_coefficient_distribution"
    EXCITATORY_CONDUCTANCE_DISTRIBUTION = "excitatory_conductance_distribution"
    EXCITATORY_CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION = (
        "excitatory_conductance_scale_factor_distribution"
    )
    EXCITATORY_FACILITATION_TIME_DISTRIBUTION = "excitatory_facilitation_time_distribution"
    EXCITATORY_DEPRESSION_TIME_DISTRIBUTION = "excitatory_depression_time_distribution"
    EXCITATORY_N_RRP_VESICLES_DISTRIBUTION = "excitatory_n_rrp_vesicles_distribution"
    EXCITATORY_DECAY_TIME_DISTRIBUTION = "excitatory_decay_time_distribution"
    EXCITATORY_U_SYN_DISTRIBUTION = "excitatory_u_syn_distribution"
    EXCITATORY_DELAY_DISTRIBUTION = "excitatory_delay_distribution"

    INHIBITORY_U_HILL_COEFFICIENT_DISTRIBUTION = "inhibitory_u_hill_coefficient_distribution"
    INHIBITORY_CONDUCTANCE_DISTRIBUTION = "inhibitory_conductance_distribution"
    INHIBITORY_CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION = (
        "inhibitory_conductance_scale_factor_distribution"
    )
    INHIBITORY_FACILITATION_TIME_DISTRIBUTION = "inhibitory_facilitation_time_distribution"
    INHIBITORY_DEPRESSION_TIME_DISTRIBUTION = "inhibitory_depression_time_distribution"
    INHIBITORY_N_RRP_VESICLES_DISTRIBUTION = "inhibitory_n_rrp_vesicles_distribution"
    INHIBITORY_DECAY_TIME_DISTRIBUTION = "inhibitory_decay_time_distribution"
    INHIBITORY_U_SYN_DISTRIBUTION = "inhibitory_u_syn_distribution"
    INHIBITORY_DELAY_DISTRIBUTION = "inhibitory_delay_distribution"

    # The model an assigner applies. Unset means the family's own default, which is the same
    # model `get_default_for` uses for the synapses no assigner claims.
    SYNAPTIC_MODEL = "synaptic_model"

    # The ends of a synapse an assigner restricts itself to. Unset means "no restriction", which
    # makes such an assigner equivalent to the all-pairs one - deliberately, since that is what
    # placing no restriction means.
    SYNAPSE_ASSIGNMENT_SOURCE = "synapse_assignment_source"
    SYNAPSE_ASSIGNMENT_TARGET = "synapse_assignment_target"

    # Operands of a combined neuron set. There is one tag per population type because each
    # combined subclass redeclares base_neuron_set and combined_with with its own reference
    # union, and an unset operand means "every neuron of the combined set's own type".
    # Named as in #947, which introduces the same tags, so the two merge without conflict.
    ANY_NEURON_SET_OPERAND = "any_neuron_set_operand"
    BIOPHYSICAL_NEURON_SET_OPERAND = "biophysical_neuron_set_operand"
    POINT_NEURON_SET_OPERAND = "point_neuron_set_operand"
    VIRTUAL_NEURON_SET_OPERAND = "virtual_neuron_set_operand"
    NON_VIRTUAL_NEURON_SET_OPERAND = "non_virtual_neuron_set_operand"

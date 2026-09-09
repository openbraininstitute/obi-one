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

Only fields with a real default belong here. An unset reference that has no answer - a synaptic
model an assigner cannot do without, say - keeps its type-keyed label, which reads as the prompt
it is rather than promising a default that does not exist.
"""

from enum import StrEnum


class ReferenceTag(StrEnum):
    """The role a block reference field plays within a task."""

    # Tsodyks-Markram parameter distributions. One per parameter rather than one for all of
    # them: each falls back to a different built-in distribution, so each needs its own answer.
    # The answers live beside those distributions, in
    # `obi_one.scientific.blocks.synaptic_models.tsodyks_markram`.
    U_HILL_COEFFICIENT_DISTRIBUTION = "u_hill_coefficient_distribution"
    CONDUCTANCE_DISTRIBUTION = "conductance_distribution"
    CONDUCTANCE_SCALE_FACTOR_DISTRIBUTION = "conductance_scale_factor_distribution"
    FACILITATION_TIME_DISTRIBUTION = "facilitation_time_distribution"
    DEPRESSION_TIME_DISTRIBUTION = "depression_time_distribution"
    N_RRP_VESICLES_DISTRIBUTION = "n_rrp_vesicles_distribution"
    DECAY_TIME_DISTRIBUTION = "decay_time_distribution"
    U_SYN_DISTRIBUTION = "u_syn_distribution"
    DELAY_DISTRIBUTION = "delay_distribution"

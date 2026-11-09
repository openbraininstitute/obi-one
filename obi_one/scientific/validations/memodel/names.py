"""Controlled vocabulary for MEModel validation result names.

These are the only names permitted for registered ValidationResult entities.
Every validation test and preset must draw its name from this enum so the
vocabulary stays consistent across the codebase and cannot drift through typos.
"""

from enum import StrEnum


class ValidationName(StrEnum):
    """Allowed validation result names (controlled vocabulary)."""

    AIS_SPIKING = "AIS Spiking Validation"
    BACK_PROPAGATING_AP = "Back-propagating Action Potential Validation"
    DEPOLARIZATION_BLOCK = "Depolarization Block Validation"
    FI_CURVE = "FI Curve Validation"
    HYPERPOLARIZATION = "Hyperpolarization Validation"
    IV_CURVE = "IV Curve Validation"
    INPUT_RESISTANCE = "Input Resistance Validation"
    SPIKING = "Spiking Validation"
    REBOUND_BURST = "Rebound Burst Validation"
    ION_CHANNEL_MODEL_BUILD = "Suitable For Ion Channel Model Build"

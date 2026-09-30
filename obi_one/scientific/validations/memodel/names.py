"""Controlled vocabulary for MEModel validation result names.

These are the only names permitted for registered ValidationResult entities.
Every validation test and preset must draw its name from this enum so the
vocabulary stays consistent across the codebase and cannot drift through typos.
"""

from enum import StrEnum


class ValidationName(StrEnum):
    """Allowed validation result names (controlled vocabulary)."""

    AIS_SPIKING = "Simulatable Neuron AIS Spiking Validation"
    BACK_PROPAGATING_AP = "Simulatable Neuron Back-propagating Action Potential Validation"
    DEPOLARIZATION_BLOCK = "Simulatable Neuron Depolarization Block Validation"
    FI_CURVE = "Simulatable Neuron FI Curve Validation"
    HYPERPOLARIZATION = "Simulatable Neuron Hyperpolarization Validation"
    IV_CURVE = "Simulatable Neuron IV Curve Validation"
    INPUT_RESISTANCE = "Simulatable Neuron Input Resistance Validation"
    SPIKING = "Simulatable Neuron Spiking Validation"
    REBOUND_BURST = "Simulatable Neuron Rebound Burst Validation"
    ION_CHANNEL_MODEL_BUILD = "Suitable For Ion Channel Model Build"

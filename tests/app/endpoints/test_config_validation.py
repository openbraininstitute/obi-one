"""Tests for the config-validation endpoint's state-key wiring."""

import pytest
from pydantic import ValidationError

from app.endpoints.config_validation import (
    _VALIDATION_CONFIG,
    EModelOptimizationScanConfig,
    SharedStatePartial,
)

# Task 2 needs the optional `emodel` extra (bluepyemodel). CI installs it; local checkouts
# often do not, in which case the key is absent by design and these tests skip. The
# bluepyemodel-absent branch is covered by
# tests/obi_one/scientific/unions_and_references/test_optional_emodel_optimization.py.
requires_emodel_extra = pytest.mark.skipif(
    EModelOptimizationScanConfig is None,
    reason="requires the optional `emodel` extra (bluepyemodel)",
)

# Parsed through SharedStatePartial only, which is what the endpoint does first and
# before db_client is touched — so nothing here reaches entitycore. The recording UUID
# is stored, not resolved; resolution happens later during generation.
VALID_FITTING_CONFIG = {
    "info": {"campaign_name": "Kv3.1 fit", "campaign_description": "From traces."},
    "initialize": {
        "recordings": {"id_str": "00000000-0000-0000-0000-000000000000"},
        "ion_channel_name": "Kv3_1",
    },
    "minf_eq": {"type": "SigFitMInf"},
    "mtau_eq": {"type": "SigFitMTau"},
    "hinf_eq": {"type": "SigFitHInf"},
    "htau_eq": {"type": "SigFitHTau"},
    "gate_exponents": {"m_power": 1, "h_power": 1},
}

# Minimal valid Task-2 config: only info, initialize and emodel_optimisation_parameters are
# required; morphology_settings / optimization_settings / optimization_params all default.
# The entity UUIDs are stored, not resolved — resolution happens during generation.
VALID_OPTIMIZATION_CONFIG = {
    "info": {
        "campaign_name": "L5PC optimization",
        "campaign_description": "Optimize an L5PC e-model.",
    },
    "initialize": {
        "emodel": "L5PC",
        "etype": {"id_str": "00000000-0000-0000-0000-000000000000"},
        "target_efeatures": {"id_str": "11111111-1111-1111-1111-111111111111"},
        "morphology": {"id_str": "22222222-2222-2222-2222-222222222222"},
    },
    "emodel_optimisation_parameters": {
        "mechanisms": {
            "ion_channel_models": [{"id_str": "33333333-3333-3333-3333-333333333333"}],
            "mechanism_regions": {
                "somatic": [
                    {"ion_channel_model": {"id_str": "33333333-3333-3333-3333-333333333333"}}
                ]
            },
        }
    },
}


def test_valid_fitting_config_parses():
    state = SharedStatePartial(ion_channel_fitting_config=VALID_FITTING_CONFIG)

    assert state.ion_channel_fitting_config.initialize.ion_channel_name == "Kv3_1"


def test_invalid_fitting_config_is_rejected():
    """Bad input fails at parse time; the endpoint turns this into HTTP 422."""
    # ion_channel_name becomes the NEURON SUFFIX, so it must be a valid identifier.
    bad = {**VALID_FITTING_CONFIG, "initialize": {**VALID_FITTING_CONFIG["initialize"]}}
    bad["initialize"]["ion_channel_name"] = "3bad-name"

    with pytest.raises(ValidationError):
        SharedStatePartial(ion_channel_fitting_config=bad)


def test_invented_equation_variant_is_rejected():
    """Guards against the model making up a plausible-sounding equation name."""
    bad = {**VALID_FITTING_CONFIG, "mtau_eq": {"type": "SigmoidalFitMTau"}}

    with pytest.raises(ValidationError):
        SharedStatePartial(ion_channel_fitting_config=bad)


def test_validation_config_covers_every_shared_state_field():
    """A field with no _VALIDATION_CONFIG entry is parsed and then never validated,
    so /validate returns valid=True having checked nothing.
    """
    fields = set(SharedStatePartial.model_fields)

    assert fields == set(_VALIDATION_CONFIG)


def test_ion_channel_fitting_does_not_execute_the_task():
    """Must stay False: the fitting task downloads NWB assets and runs nrnivmodl."""
    assert _VALIDATION_CONFIG["ion_channel_fitting_config"] is False


@requires_emodel_extra
def test_valid_optimization_config_parses():
    state = SharedStatePartial(emodel_optimization_config=VALID_OPTIMIZATION_CONFIG)

    assert state.emodel_optimization_config.initialize.emodel == "L5PC"


@requires_emodel_extra
def test_optimization_config_rejects_incomplete_initialize():
    """All four `initialize` fields are required; dropping one must fail at parse time."""
    initialize = {
        k: v for k, v in VALID_OPTIMIZATION_CONFIG["initialize"].items() if k != "target_efeatures"
    }
    bad = {**VALID_OPTIMIZATION_CONFIG, "initialize": initialize}

    with pytest.raises(ValidationError):
        SharedStatePartial(emodel_optimization_config=bad)


@requires_emodel_extra
def test_optimization_config_rejects_empty_mechanisms():
    """`ion_channel_models` and `mechanism_regions` both have min_length=1."""
    bad = {
        **VALID_OPTIMIZATION_CONFIG,
        "emodel_optimisation_parameters": {
            "mechanisms": {"ion_channel_models": [], "mechanism_regions": {}}
        },
    }

    with pytest.raises(ValidationError):
        SharedStatePartial(emodel_optimization_config=bad)


@requires_emodel_extra
def test_emodel_optimization_does_not_execute_the_task():
    """Must stay False: the task runs a BluePyEModel/NEURON optimisation.

    Registration also calls `upload_directory`, which the validator's write interception
    does not cover, so executing it would perform a real write during validation.
    """
    assert _VALIDATION_CONFIG["emodel_optimization_config"] is False

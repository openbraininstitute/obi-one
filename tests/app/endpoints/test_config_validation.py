"""Tests for the config-validation endpoint's state-key wiring."""

import pytest
from pydantic import ValidationError

from app.endpoints.config_validation import _VALIDATION_CONFIG, SharedStatePartial

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

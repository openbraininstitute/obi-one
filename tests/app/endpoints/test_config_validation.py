"""Tests for the config-validation endpoint's state-key wiring.

``SharedStatePartial`` and ``_VALIDATION_CONFIG`` are two hand-maintained lists that
must stay in step. A field present on the model but missing from the dict is parsed
and then never validated, so ``/config-validation/validate`` returns ``valid=True``
having checked nothing — a silent false pass. These tests guard that drift.
"""

from app.endpoints.config_validation import _VALIDATION_CONFIG, SharedStatePartial


def test_validation_config_covers_every_shared_state_field():
    """Every field must have a _VALIDATION_CONFIG entry, and vice versa."""
    fields = set(SharedStatePartial.model_fields)
    configured = set(_VALIDATION_CONFIG)

    assert fields == configured, (
        "SharedStatePartial and _VALIDATION_CONFIG have drifted. "
        f"Fields missing an entry (parsed but never validated): {fields - configured}. "
        f"Entries with no field (never reachable): {configured - fields}."
    )


def test_ion_channel_fitting_config_is_wired():
    """Build > Ion Channel state key is present and validated (prod-ai#103)."""
    assert "ion_channel_fitting_config" in SharedStatePartial.model_fields
    assert "ion_channel_fitting_config" in _VALIDATION_CONFIG


def test_ion_channel_fitting_does_not_execute_the_task():
    """Must stay False: the fitting task downloads NWB assets and runs nrnivmodl.

    Generation alone still resolves the input recording against the database, so
    this keeps validation useful without making it expensive.
    """
    assert _VALIDATION_CONFIG["ion_channel_fitting_config"] is False


def test_fitting_and_simulation_ion_channel_keys_are_distinct():
    """The two ion-channel keys mean different things and must not be conflated.

    ``ion_channel_model_simulation_config`` simulates an existing model;
    ``ion_channel_fitting_config`` builds a new one from experimental traces.
    """
    fields = SharedStatePartial.model_fields
    assert "ion_channel_model_simulation_config" in fields
    assert "ion_channel_fitting_config" in fields
    assert (
        fields["ion_channel_model_simulation_config"].annotation
        != fields["ion_channel_fitting_config"].annotation
    )


def test_unknown_state_keys_are_ignored_not_rejected():
    """Documents why obi-one must deploy before its clients.

    ``SharedStatePartial`` has no ``extra='forbid'``, so an older obi-one silently
    drops a state key it does not know and reports success. Shipping a client that
    sends a new key before obi-one supports it therefore yields a false pass rather
    than an error.
    """
    state = SharedStatePartial(some_future_config={"anything": 1})
    assert not hasattr(state, "some_future_config")

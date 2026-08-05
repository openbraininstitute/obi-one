"""The error bodies the two scan-config endpoints answer with.

The UI posts a config to ``grid-scan-coordinate-count`` and then to ``*-generate-grid``, so the
two have to fail in the same shape or the caller needs a different reader per endpoint. They used
to disagree three ways: a rejected config was a 400 ``{detail}`` on one and a 422
``{error_code, message, details}`` on the other, and an unexpected failure was plain-text
``Internal Server Error`` on one -- not even JSON -- and a 500 ``{detail}`` on the other.

These tests pin the agreement rather than each endpoint separately, so the two cannot drift apart
again.
"""

import json

import pytest

import obi_one as obi
from app.dependencies.entitysdk import get_client
from obi_one.core.exception import ConfigValidationError
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
)

from tests.utils import CIRCUIT_DIR

COUNT_ENDPOINT = "/declared/scan_config/grid-scan-coordinate-count"
GENERATE_ENDPOINT = "/generated/circuit-simulation-scan-config-generate-grid"
BOTH_ENDPOINTS = [COUNT_ENDPOINT, GENERATE_ENDPOINT]

# The first thing each endpoint calls on the task, so patching it exercises that endpoint's own
# error handling rather than something they happen to share.
FAILURE_HOOK = {
    COUNT_ENDPOINT: "multiple_value_parameters",
    GENERATE_ENDPOINT: "execute",
}

CIRCUIT_PATH = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"

DEPRECATION_MESSAGE = (
    "AllNeurons is deprecated and should not be used. Please use an alternative neuron set instead."
)

# Above MAX_N_COORDINATES (100), so the count endpoint rejects it.
OVERSIZED_SWEEP = [float(i) for i in range(200)]


def _payload(amplitude):
    config = CircuitSimulationScanConfig.empty_config()
    config.set(
        obi.Info(campaign_name="Test campaign", campaign_description="Test description"),
        name="info",
    )
    neuron_set = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    config.add(neuron_set, name="my_set")
    # A block carrying a reference, so a test can point that reference at nothing.
    config.add(
        obi.ConstantCurrentClampSomaticStimulus(
            neuron_set=neuron_set.ref, amplitude=amplitude, duration=50.0
        ),
        name="stim",
    )
    config.set(
        CircuitSimulationScanConfig.Initialize(
            circuit=obi.Circuit(name="c", path=str(CIRCUIT_PATH)),
            simulation_length=100.0,
        ),
        name="initialize",
    )
    config.fill_block_references_and_names()
    return json.loads(config.model_dump_json())


@pytest.fixture
def payload():
    """A body that passes request validation, so the request reaches the endpoint itself.

    What the endpoint then does with it is irrelevant to most tests here -- they replace the call
    it makes -- but the body still has to deserialize or FastAPI rejects it with its own 422 and
    the endpoint's error handling is never exercised.
    """
    return _payload(0.1)


_STUB_DB_CLIENT = object()


@pytest.fixture
def _stub_db_client(client, monkeypatch):
    """The generate endpoint only hands the client on to generation, which the tests replace."""
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: _STUB_DB_CLIENT)


def assert_error_envelope(response, *, status, reason):
    """Both endpoints answer errors in one envelope, with the reason in ``details[0].msg``.

    ``details[0].msg`` and not ``message``: request-validation failures are turned into this
    envelope by a global handler that puts a generic "Validation error" in ``message`` and the
    specifics in ``details``. So ``details[0].msg`` is the only field that always carries the
    reason, which is why the web app reads it. Errors raised by an endpoint itself do also name
    the reason in ``message`` -- asserted at those call sites.

    Returns the parsed body so callers can make their own extra assertions.
    """
    assert response.status_code == status, response.text

    body = response.json()  # Must be JSON: a caller that parses first fails on plain text.
    assert set(body) == {"error_code", "message", "details"}
    assert body["message"], "an empty message leaves a caller reading it with nothing to show"
    assert reason in body["details"][0]["msg"]
    return body


@pytest.mark.usefixtures("_stub_db_client")
@pytest.mark.parametrize("endpoint", BOTH_ENDPOINTS)
def test_dangling_block_reference_is_a_client_error(client, payload, endpoint):
    """A reference to a block that does not exist is rejected identically by both endpoints.

    Resolution happens in a model validator, so this never reaches either endpoint -- pydantic
    rejects it, which only happens because the underlying raise is a ValueError. A typo, or a
    block deleted while something still targets it, is an ordinary mistake and not a server fault.
    """
    payload["stimuli"]["stim"]["neuron_set"]["block_name"] = "does_not_exist"

    response = client.post(endpoint, json=payload)

    assert_error_envelope(response, status=422, reason="does_not_exist")


@pytest.mark.usefixtures("_stub_db_client")
@pytest.mark.parametrize("endpoint", BOTH_ENDPOINTS)
def test_unrunnable_config_is_a_client_error(client, monkeypatch, payload, endpoint):
    """A config that parsed but cannot be used is a 422 naming the offending block, on both.

    Without a typed handler ahead of the blanket ``except Exception`` this was a 500, which gave
    the UI an opaque "Internal Server Error" and paged Sentry as though the server were at fault.
    """

    def _raise(*_args, **_kwargs):
        raise ConfigValidationError(DEPRECATION_MESSAGE)

    monkeypatch.setattr(GridScanGenerationTask, FAILURE_HOOK[endpoint], _raise)

    response = client.post(endpoint, json=payload)

    body = assert_error_envelope(response, status=422, reason=DEPRECATION_MESSAGE)
    assert body["message"] == DEPRECATION_MESSAGE
    assert body["error_code"] == "INVALID_REQUEST"


@pytest.mark.usefixtures("_stub_db_client")
@pytest.mark.parametrize("endpoint", BOTH_ENDPOINTS)
def test_unexpected_failure_is_a_500_in_the_same_shape(client, monkeypatch, payload, endpoint):
    """Genuine server faults stay 500 -- not masked as client errors -- but answer in JSON.

    The count endpoint used to let these escape as Starlette's plain-text "Internal Server Error";
    a caller that parses the body before inspecting it failed on the parse rather than reporting
    the error, so `assert_error_envelope` calling `.json()` is the assertion that matters here.
    """
    message = "circuit file is corrupt"

    def _raise(*_args, **_kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(GridScanGenerationTask, FAILURE_HOOK[endpoint], _raise)

    response = client.post(endpoint, json=payload)

    body = assert_error_envelope(response, status=500, reason=message)
    assert body["error_code"] == "INTERNAL_ERROR"


def test_too_many_coordinates_is_a_client_error(client):
    """Count's own rejection uses the shared envelope too, rather than FastAPI's `{detail}`."""
    response = client.post(COUNT_ENDPOINT, json=_payload(OVERSIZED_SWEEP))

    assert_error_envelope(response, status=422, reason="exceeds maximum allowed 100")


def test_coordinate_count_succeeds_for_a_valid_config(client, payload):
    """The success path is untouched by the error-handling changes."""
    response = client.post(COUNT_ENDPOINT, json=payload)

    assert response.status_code == 200, response.text
    assert response.json() == 1

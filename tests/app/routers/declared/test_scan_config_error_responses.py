"""The count and generate endpoints must fail in the same shape, since the UI posts to both."""

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

# The first thing each endpoint calls on the task, so patching it reaches that endpoint's own
# error handling.
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
    # Carries a reference, so a test can point that reference at nothing.
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
    """A body that passes request validation, so the request reaches the endpoint itself."""
    return _payload(0.1)


_STUB_DB_CLIENT = object()


@pytest.fixture
def _stub_db_client(client, monkeypatch):
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: _STUB_DB_CLIENT)


def assert_error_envelope(response, *, status, reason):
    # `details[0].msg` and not `message`: request validation failures put a generic
    # "Validation error" in `message`, so only `details` always carries the reason.
    assert response.status_code == status, response.text

    body = response.json()
    assert set(body) == {"error_code", "message", "details"}
    assert body["message"]
    assert reason in body["details"][0]["msg"]
    return body


@pytest.mark.usefixtures("_stub_db_client")
@pytest.mark.parametrize("endpoint", BOTH_ENDPOINTS)
def test_dangling_block_reference_is_a_client_error(client, payload, endpoint):
    payload["stimuli"]["stim"]["neuron_set"]["block_name"] = "does_not_exist"

    response = client.post(endpoint, json=payload)

    assert_error_envelope(response, status=422, reason="does_not_exist")


@pytest.mark.usefixtures("_stub_db_client")
@pytest.mark.parametrize("endpoint", BOTH_ENDPOINTS)
def test_unrunnable_config_is_a_client_error(client, monkeypatch, payload, endpoint):
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
    message = "circuit file is corrupt"

    def _raise(*_args, **_kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(GridScanGenerationTask, FAILURE_HOOK[endpoint], _raise)

    response = client.post(endpoint, json=payload)

    body = assert_error_envelope(response, status=500, reason=message)
    assert body["error_code"] == "INTERNAL_ERROR"


def test_too_many_coordinates_is_a_client_error(client):
    response = client.post(COUNT_ENDPOINT, json=_payload(OVERSIZED_SWEEP))

    assert_error_envelope(response, status=422, reason="exceeds maximum allowed 100")


def test_coordinate_count_succeeds_for_a_valid_config(client, payload):
    response = client.post(COUNT_ENDPOINT, json=payload)

    assert response.status_code == 200, response.text
    assert response.json() == 1

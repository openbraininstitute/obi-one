"""How the /generated/* endpoints surface a config that is valid but not runnable.

A config using a deprecated neuron set deserializes fine -- that is deliberate, so legacy
campaigns stay openable in the UI -- and only fails once generation resolves it against a
circuit. That failure is the caller's problem (migrate the config), not a server fault, so it
must reach them as a 4xx carrying the reason rather than an opaque 500.
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

ENDPOINT = "/generated/circuit-simulation-scan-config-generate-grid"

CIRCUIT_PATH = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"

DEPRECATION_MESSAGE = (
    "AllNeurons is deprecated and should not be used. Please use an alternative neuron set instead."
)


@pytest.fixture
def payload():
    """A body that passes request validation, so the request reaches the endpoint itself.

    What generation then does with it is irrelevant here -- every test in this module replaces
    ``execute`` -- but the body still has to deserialize or FastAPI rejects it with its own 422
    and the endpoint's error handling is never exercised.
    """
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
            neuron_set=neuron_set.ref, amplitude=0.1, duration=50.0
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


_STUB_DB_CLIENT = object()


@pytest.fixture
def _stub_db_client(client, monkeypatch):
    """The endpoint only hands the client to generation, which every test here replaces."""
    monkeypatch.setitem(client.app.dependency_overrides, get_client, lambda: _STUB_DB_CLIENT)


@pytest.mark.usefixtures("_stub_db_client")
def test_unrunnable_config_is_a_client_error_not_a_500(client, monkeypatch, payload):
    """A ConfigValidationError from generation becomes a 422 that names the offending block.

    Pinned because the endpoint's blanket ``except Exception`` maps everything else to a 500;
    without the typed handler in front of it a deprecated neuron set gave the UI an opaque
    "Internal Server Error" and paged Sentry as a server fault.
    """

    def _raise(*_args, **_kwargs):
        raise ConfigValidationError(DEPRECATION_MESSAGE)

    monkeypatch.setattr(GridScanGenerationTask, "execute", _raise)

    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error_code"] == "INVALID_REQUEST"
    assert body["message"] == DEPRECATION_MESSAGE

    # The frontend reads `details[0].msg` for any non-500 and shows a bare
    # "An error occurred generating the simulation campaign" when it is missing, so the reason
    # has to be here and not only in `message`.
    assert body["details"][0]["msg"] == DEPRECATION_MESSAGE


@pytest.mark.usefixtures("_stub_db_client")
def test_dangling_block_reference_is_a_client_error(client, payload):
    """A reference to a block that does not exist is rejected during body validation.

    Resolution happens in a model validator, so this never reaches the endpoint at all -- it is
    pydantic that has to reject it, which only happens if the underlying raise is a ValueError.
    A typo or a deleted block is an ordinary user mistake and must not read as a server fault.
    """
    payload["stimuli"]["stim"]["neuron_set"]["block_name"] = "does_not_exist"

    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 422, response.text
    assert "does_not_exist" in response.text


@pytest.mark.usefixtures("_stub_db_client")
def test_unexpected_failure_is_still_a_500(client, monkeypatch, payload):
    """Genuine server faults must still report as 500, not be masked as client errors."""

    def _raise(*_args, **_kwargs):
        msg = "circuit file is corrupt"
        raise RuntimeError(msg)

    monkeypatch.setattr(GridScanGenerationTask, "execute", _raise)

    response = client.post(ENDPOINT, json=payload)

    assert response.status_code == 500, response.text

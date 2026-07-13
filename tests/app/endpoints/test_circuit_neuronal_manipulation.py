"""Tests for the neuronal manipulation endpoints in circuit_properties.py."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import entitysdk.exception
import pytest
from fastapi.testclient import TestClient

from app.application import app
from app.dependencies.entitysdk import get_client

from tests.utils import AUTH_HEADER_USER_1, PROJECT_HEADERS


@pytest.fixture
def _mock_client():
    mock = MagicMock()
    app.dependency_overrides[get_client] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_client, None)


@pytest.fixture
def client(_override_check_user_info, _mock_client):
    """Test client with mocked db_client dependency."""
    with TestClient(app) as c:
        yield c


class TestNeuronalManipulationPropertiesEndpoint:
    """Tests for POST /declared/neuronal-manipulation-properties."""

    def test_memodel_path(self, client):
        """When entity_id is an MEModel, returns mechanism variables directly."""
        with patch("app.endpoints.circuit_properties.try_get_mechanism_variables") as mock_try:
            mock_try.return_value = {"NaTg": {"section_lists": ["somatic"], "variables": {}}}

            response = client.post(
                "/declared/neuronal-manipulation-properties",
                json={"entity_id": str(uuid4())},
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "memodel"
        assert "MechanismVariablesByIonChannel" in data

    def test_circuit_path_with_neuron_set(self, client):
        """Circuit path with neuron_set."""
        with (
            patch(
                "app.endpoints.circuit_properties.try_get_mechanism_variables",
                return_value=None,
            ),
            patch(
                "app.endpoints.circuit_properties.get_circuit_manipulation_properties"
            ) as mock_props,
        ):
            mock_props.return_value = {
                "entity_type": "circuit",
                "populations": ["S1nonbarrel_neurons"],
                "MechanismVariablesByIonChannel": {"NaTg": {}},
                "warnings": None,
            }

            response = client.post(
                "/declared/neuronal-manipulation-properties",
                json={
                    "entity_id": str(uuid4()),
                    "neuron_set": {"type": "PredefinedNeuronSet", "node_set": "All"},
                },
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "circuit"
        assert data["populations"] == ["S1nonbarrel_neurons"]
        assert "MechanismVariablesByIonChannel" in data

    def test_circuit_path_no_neuron_set_uses_fast_path(self, client):
        """Circuit entity without neuron_set or node_ids uses fast path (all derivations)."""
        with (
            patch(
                "app.endpoints.circuit_properties.try_get_mechanism_variables",
                return_value=None,
            ),
            patch(
                "app.endpoints.circuit_properties.get_circuit_manipulation_properties"
            ) as mock_props,
        ):
            mock_props.return_value = {
                "entity_type": "circuit",
                "population": None,
                "MechanismVariablesByIonChannel": {"NaTg": {}},
                "warnings": None,
            }

            response = client.post(
                "/declared/neuronal-manipulation-properties",
                json={"entity_id": str(uuid4())},
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "circuit"

    def test_circuit_path_value_error(self, client):
        """ValueError from library returns 400."""
        with (
            patch(
                "app.endpoints.circuit_properties.try_get_mechanism_variables",
                return_value=None,
            ),
            patch(
                "app.endpoints.circuit_properties.get_circuit_manipulation_properties",
                side_effect=ValueError("bad input"),
            ),
        ):
            response = client.post(
                "/declared/neuronal-manipulation-properties",
                json={
                    "entity_id": str(uuid4()),
                    "neuron_set": {"type": "PredefinedNeuronSet", "node_set": "All"},
                },
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 400

    def test_circuit_path_sdk_error(self, client):
        """EntitySDKError from library returns 500."""
        with (
            patch(
                "app.endpoints.circuit_properties.try_get_mechanism_variables",
                return_value=None,
            ),
            patch(
                "app.endpoints.circuit_properties.get_circuit_manipulation_properties",
                side_effect=entitysdk.exception.EntitySDKError("internal"),
            ),
        ):
            response = client.post(
                "/declared/neuronal-manipulation-properties",
                json={
                    "entity_id": str(uuid4()),
                    "neuron_set": {"type": "PredefinedNeuronSet", "node_set": "All"},
                },
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 500


class TestNodeIdsEndpoint:
    """Tests for POST /declared/circuit/{circuit_id}/node-ids."""

    def test_success(self, client):
        """Successfully resolves neuron set to node IDs."""
        with patch("app.endpoints.circuit_properties.get_circuit_node_ids") as mock_node_ids:
            mock_node_ids.return_value = {"S1nonbarrel_neurons": [0, 1, 2, 3]}

            response = client.post(
                f"/declared/circuit/{uuid4()}/node-ids",
                json={"neuron_set": {"type": "PredefinedNeuronSet", "node_set": "All"}},
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["node_ids_per_population"] == {"S1nonbarrel_neurons": [0, 1, 2, 3]}

    def test_value_error(self, client):
        """ValueError returns 400."""
        with patch(
            "app.endpoints.circuit_properties.get_circuit_node_ids",
            side_effect=ValueError("no sonata asset"),
        ):
            response = client.post(
                f"/declared/circuit/{uuid4()}/node-ids",
                json={"neuron_set": {"type": "PredefinedNeuronSet", "node_set": "All"}},
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 400

    def test_sdk_error(self, client):
        """EntitySDKError returns 500."""
        with patch(
            "app.endpoints.circuit_properties.get_circuit_node_ids",
            side_effect=entitysdk.exception.EntitySDKError("not found"),
        ):
            response = client.post(
                f"/declared/circuit/{uuid4()}/node-ids",
                json={"neuron_set": {"type": "PredefinedNeuronSet", "node_set": "All"}},
                headers={**AUTH_HEADER_USER_1, **PROJECT_HEADERS},
            )

        assert response.status_code == 500

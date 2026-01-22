"""Unit tests for task launch endpoints."""

import uuid
from decimal import Decimal
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock

import entitysdk.client
import pytest
from fastapi import HTTPException
from obp_accounting_sdk._async.factory import AsyncAccountingSessionFactory
from obp_accounting_sdk.constants import ServiceSubtype

from app.dependencies.accounting import get_accounting_factory
from app.dependencies.entitysdk import get_client as get_db_client
from app.endpoints.task_launch import TaskType, _evaluate_accounting_parameters

ROUTE_ESTIMATE = "/declared/estimate"


@pytest.fixture
def mock_simulation_entity():
    """Mock Simulation entity."""
    simulation = MagicMock()
    simulation.entity_id = uuid.uuid4()
    simulation.neuron_count = 1000
    return simulation


@pytest.fixture
def mock_circuit_entity_small():
    """Mock Circuit entity with small scale."""
    circuit = MagicMock()
    circuit.scale = "small"
    return circuit


@pytest.fixture
def mock_circuit_entity_microcircuit():
    """Mock Circuit entity with microcircuit scale."""
    circuit = MagicMock()
    circuit.scale = "microcircuit"
    return circuit


@pytest.fixture
def mock_circuit_entity_region():
    """Mock Circuit entity with region scale."""
    circuit = MagicMock()
    circuit.scale = "region"
    return circuit


@pytest.fixture
def mock_circuit_entity_system():
    """Mock Circuit entity with system scale."""
    circuit = MagicMock()
    circuit.scale = "system"
    return circuit


@pytest.fixture
def mock_circuit_entity_whole_brain():
    """Mock Circuit entity with whole_brain scale."""
    circuit = MagicMock()
    circuit.scale = "whole_brain"
    return circuit


@pytest.fixture
def mock_db_client():
    """Mock entitysdk client."""
    return MagicMock(spec=entitysdk.client.Client)


@pytest.fixture
def mock_accounting_factory():
    """Mock accounting factory."""
    factory = MagicMock(spec=AsyncAccountingSessionFactory)
    factory.estimate_oneshot_cost = AsyncMock(return_value=Decimal("10.5"))
    return factory


class TestEvaluateAccountingParameters:
    """Tests for _evaluate_accounting_parameters function."""

    @classmethod
    def test_simulation_small_scale(
        cls,
        mock_db_client,
        mock_simulation_entity,
        mock_circuit_entity_small,
    ):
        """Test evaluation for Simulation with small circuit scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            mock_circuit_entity_small,
        ]

        result = _evaluate_accounting_parameters(
            db_client=mock_db_client,
            task_type=TaskType.circuit_simulation,
            entity_id=circuit_id,
        )

        assert result["service_subtype"] == ServiceSubtype.SMALL_SIM
        assert result["count"] == 1000
        assert mock_db_client.get_entity.call_count == 2
        mock_db_client.get_entity.assert_any_call(
            entity_id=circuit_id, entity_type=entitysdk.models.Simulation
        )
        mock_db_client.get_entity.assert_any_call(
            entity_id=circuit_id, entity_type=entitysdk.models.Circuit
        )

    @classmethod
    def test_simulation_microcircuit_scale(
        cls,
        mock_db_client,
        mock_simulation_entity,
        mock_circuit_entity_microcircuit,
    ):
        """Test evaluation for Simulation with microcircuit scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            mock_circuit_entity_microcircuit,
        ]

        result = _evaluate_accounting_parameters(
            db_client=mock_db_client,
            task_type=TaskType.circuit_simulation,
            entity_id=circuit_id,
        )

        assert result["service_subtype"] == ServiceSubtype.MICROCIRCUIT_SIM
        assert result["count"] == 1000

    @classmethod
    def test_simulation_region_scale(
        cls,
        mock_db_client,
        mock_simulation_entity,
        mock_circuit_entity_region,
    ):
        """Test evaluation for Simulation with region scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            mock_circuit_entity_region,
        ]

        result = _evaluate_accounting_parameters(
            db_client=mock_db_client,
            task_type=TaskType.circuit_simulation,
            entity_id=circuit_id,
        )

        assert result["service_subtype"] == ServiceSubtype.REGION_SIM
        assert result["count"] == 1000

    @classmethod
    def test_simulation_system_scale(
        cls,
        mock_db_client,
        mock_simulation_entity,
        mock_circuit_entity_system,
    ):
        """Test evaluation for Simulation with system scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            mock_circuit_entity_system,
        ]

        result = _evaluate_accounting_parameters(
            db_client=mock_db_client,
            task_type=TaskType.circuit_simulation,
            entity_id=circuit_id,
        )

        assert result["service_subtype"] == ServiceSubtype.SYSTEM_SIM
        assert result["count"] == 1000

    @classmethod
    def test_simulation_whole_brain_scale(
        cls,
        mock_db_client,
        mock_simulation_entity,
        mock_circuit_entity_whole_brain,
    ):
        """Test evaluation for Simulation with whole_brain scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            mock_circuit_entity_whole_brain,
        ]

        result = _evaluate_accounting_parameters(
            db_client=mock_db_client,
            task_type=TaskType.circuit_simulation,
            entity_id=circuit_id,
        )

        assert result["service_subtype"] == ServiceSubtype.WHOLE_BRAIN_SIM
        assert result["count"] == 1000

    @classmethod
    def test_simulation_unsupported_scale(
        cls,
        mock_db_client,
        mock_simulation_entity,
    ):
        """Test evaluation for Simulation with unsupported circuit scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        circuit_entity = MagicMock()
        circuit_entity.scale = "unknown_scale"

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            circuit_entity,
        ]

        with pytest.raises(HTTPException) as exc_info:
            _evaluate_accounting_parameters(
                db_client=mock_db_client,
                task_type=TaskType.circuit_simulation,
                entity_id=circuit_id,
            )
        assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
        assert "Unsupported circuit scale" in exc_info.value.detail

    @classmethod
    def test_circuit_extraction(
        cls,
        mock_db_client,
        mock_simulation_entity,
    ):
        """Test evaluation for CircuitExtraction config type."""
        circuit_id = str(mock_simulation_entity.entity_id)

        result = _evaluate_accounting_parameters(
            db_client=mock_db_client,
            task_type=TaskType.circuit_extraction,
            entity_id=circuit_id,
        )

        assert result["service_subtype"] == ServiceSubtype.SMALL_CIRCUIT_SIM
        assert result["count"] == 1
        # Should not call get_entity for non-Simulation types
        mock_db_client.get_entity.assert_not_called()


class TestEstimateEndpoint:
    """Tests for the /estimate endpoint."""

    @classmethod
    def test_estimate_simulation_small_scale(
        cls,
        client,
        mock_db_client,
        mock_simulation_entity,
        mock_circuit_entity_small,
        mock_accounting_factory,
        monkeypatch,
    ):
        """Test estimate endpoint for Simulation with small scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        # Setup project context
        project_context = MagicMock()
        project_context.project_id = uuid.uuid4()
        project_context.virtual_lab_id = uuid.uuid4()
        mock_db_client.project_context = project_context

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            mock_circuit_entity_small,
        ]

        # Override dependencies
        monkeypatch.setitem(client.app.dependency_overrides, get_db_client, lambda: mock_db_client)
        monkeypatch.setitem(
            client.app.dependency_overrides,
            get_accounting_factory,
            lambda: mock_accounting_factory,
        )

        response = client.post(
            ROUTE_ESTIMATE,
            json={"task_type": TaskType.circuit_simulation, "config_id": circuit_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert "cost" in data
        assert "accounting_parameters" in data
        assert data["accounting_parameters"]["service_subtype"] == "small-sim"
        assert data["accounting_parameters"]["count"] == 1000

        # Verify accounting factory was called correctly
        mock_accounting_factory.estimate_oneshot_cost.assert_called_once()
        call_kwargs = mock_accounting_factory.estimate_oneshot_cost.call_args[1]
        assert call_kwargs["subtype"] == ServiceSubtype.SMALL_SIM
        assert call_kwargs["count"] == 1000
        assert call_kwargs["proj_id"] == str(project_context.project_id)
        assert call_kwargs["vlab_id"] == str(project_context.virtual_lab_id)

    @classmethod
    def test_estimate_circuit_extraction(
        cls,
        client,
        mock_db_client,
        mock_accounting_factory,
        mock_simulation_entity,
        monkeypatch,
    ):
        """Test estimate endpoint for CircuitExtraction."""
        circuit_id = str(mock_simulation_entity.entity_id)

        # Setup project context
        project_context = MagicMock()
        project_context.project_id = uuid.uuid4()
        project_context.virtual_lab_id = uuid.uuid4()
        mock_db_client.project_context = project_context

        # Override dependencies
        monkeypatch.setitem(client.app.dependency_overrides, get_db_client, lambda: mock_db_client)
        monkeypatch.setitem(
            client.app.dependency_overrides,
            get_accounting_factory,
            lambda: mock_accounting_factory,
        )

        response = client.post(
            ROUTE_ESTIMATE,
            json={"task_type": TaskType.circuit_extraction, "config_id": circuit_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert "cost" in data
        assert "accounting_parameters" in data
        assert data["accounting_parameters"]["service_subtype"] == "small-circuit-sim"
        assert data["accounting_parameters"]["count"] == 1

        # Verify accounting factory was called correctly
        mock_accounting_factory.estimate_oneshot_cost.assert_called_once()
        call_kwargs = mock_accounting_factory.estimate_oneshot_cost.call_args[1]
        assert call_kwargs["subtype"] == ServiceSubtype.SMALL_CIRCUIT_SIM
        assert call_kwargs["count"] == 1

    @classmethod
    def test_estimate_no_project_context(
        cls,
        client,
        mock_db_client,
        mock_accounting_factory,
        mock_simulation_entity,
        monkeypatch,
    ):
        """Test estimate endpoint fails when project context is missing."""
        circuit_id = str(mock_simulation_entity.entity_id)

        # No project context
        mock_db_client.project_context = None

        # Override dependencies
        monkeypatch.setitem(client.app.dependency_overrides, get_db_client, lambda: mock_db_client)
        monkeypatch.setitem(
            client.app.dependency_overrides,
            get_accounting_factory,
            lambda: mock_accounting_factory,
        )

        response = client.post(
            ROUTE_ESTIMATE,
            json={"task_type": TaskType.circuit_extraction, "config_id": circuit_id},
        )

        assert response.status_code == 400
        assert "Project context is required" in response.json()["detail"]

    @classmethod
    def test_estimate_unsupported_scale(
        cls,
        client,
        mock_db_client,
        mock_simulation_entity,
        mock_accounting_factory,
        monkeypatch,
    ):
        """Test estimate endpoint fails for unsupported circuit scale."""
        circuit_id = str(mock_simulation_entity.entity_id)

        # Setup project context
        project_context = MagicMock()
        project_context.project_id = uuid.uuid4()
        project_context.virtual_lab_id = uuid.uuid4()
        mock_db_client.project_context = project_context

        circuit_entity = MagicMock()
        circuit_entity.scale = "unknown_scale"

        mock_db_client.get_entity.side_effect = [
            mock_simulation_entity,
            circuit_entity,
        ]

        # Override dependencies
        monkeypatch.setitem(client.app.dependency_overrides, get_db_client, lambda: mock_db_client)
        monkeypatch.setitem(
            client.app.dependency_overrides,
            get_accounting_factory,
            lambda: mock_accounting_factory,
        )

        response = client.post(
            ROUTE_ESTIMATE,
            json={"task_type": TaskType.circuit_simulation, "config_id": circuit_id},
        )

        assert response.status_code == 400, (
            f"Expected 400, got {response.status_code}. Response: {response.text}"
        )
        response_json = response.json()
        assert "detail" in response_json, f"Response JSON: {response_json}"
        assert "Unsupported circuit scale" in response_json["detail"]

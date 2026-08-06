"""Unit tests for _check_circuit_is_active in task endpoint."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError

from app.endpoints.task import _check_circuit_is_active
from app.errors import ApiError


def _circuit(*, lifecycle_status: str | None, root_circuit_id=None) -> MagicMock:
    circuit = MagicMock()
    circuit.root_circuit_id = root_circuit_id
    circuit.lifecycle_status = lifecycle_status
    return circuit


def _db_with_circuit(circuit: MagicMock) -> MagicMock:
    db_client = MagicMock()
    sim = MagicMock()
    sim.entity_id = uuid4()
    db_client.get_entity.side_effect = [sim, circuit]
    return db_client


class TestCheckCircuitIsActive:
    def test_active_circuit_passes(self):
        """Active circuit should not raise, customized or not."""
        circuit = _circuit(lifecycle_status="active", root_circuit_id=uuid4())
        _check_circuit_is_active(_db_with_circuit(circuit), uuid4())

    def test_active_registered_circuit_passes(self):
        """Active registered circuit (no root) should not raise."""
        circuit = _circuit(lifecycle_status="active", root_circuit_id=None)
        _check_circuit_is_active(_db_with_circuit(circuit), uuid4())

    def test_draft_circuit_raises(self):
        """Draft circuit should be rejected."""
        circuit = _circuit(lifecycle_status="draft", root_circuit_id=uuid4())
        with pytest.raises(ApiError, match="not ready for simulation"):
            _check_circuit_is_active(_db_with_circuit(circuit), uuid4())

    def test_draft_registered_circuit_raises(self):
        """Draft registered circuit (no root) should also be rejected."""
        circuit = _circuit(lifecycle_status="draft", root_circuit_id=None)
        with pytest.raises(ApiError, match="not ready for simulation"):
            _check_circuit_is_active(_db_with_circuit(circuit), uuid4())

    def test_disqualified_circuit_raises(self):
        """Disqualified circuit should be rejected."""
        circuit = _circuit(lifecycle_status="disqualified", root_circuit_id=uuid4())
        with pytest.raises(ApiError, match="not ready for simulation"):
            _check_circuit_is_active(_db_with_circuit(circuit), uuid4())

    def test_missing_lifecycle_status_raises(self):
        """Circuit with no lifecycle_status should be rejected."""
        circuit = _circuit(lifecycle_status=None, root_circuit_id=None)
        with pytest.raises(ApiError, match="not ready for simulation"):
            _check_circuit_is_active(_db_with_circuit(circuit), uuid4())

    def test_entity_not_found_passes(self):
        """If simulation or circuit can't be fetched, gate is skipped."""
        db_client = MagicMock()
        db_client.get_entity.side_effect = EntitySDKError("not found")
        _check_circuit_is_active(db_client, uuid4())

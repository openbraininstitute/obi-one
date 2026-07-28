"""Unit tests for _check_circuit_is_active in task endpoint."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.exception import EntitySDKError

from app.endpoints.task import _check_circuit_is_active
from app.errors import ApiError


class TestCheckCircuitIsActive:
    def test_active_circuit_passes(self):
        """Active customized circuit should not raise."""
        db_client = MagicMock()
        sim = MagicMock()
        sim.entity_id = uuid4()
        circuit = MagicMock()
        circuit.root_circuit_id = uuid4()  # customized circuit
        circuit.lifecycle_status = "active"

        db_client.get_entity.side_effect = [sim, circuit]
        _check_circuit_is_active(db_client, uuid4())  # should not raise

    def test_draft_circuit_raises(self):
        """Draft customized circuit should be rejected."""
        db_client = MagicMock()
        sim = MagicMock()
        sim.entity_id = uuid4()
        circuit = MagicMock()
        circuit.root_circuit_id = uuid4()  # customized circuit
        circuit.lifecycle_status = "draft"

        db_client.get_entity.side_effect = [sim, circuit]
        with pytest.raises(ApiError, match="not ready for simulation"):
            _check_circuit_is_active(db_client, uuid4())

    def test_disqualified_circuit_raises(self):
        """Disqualified circuit should be rejected."""
        db_client = MagicMock()
        sim = MagicMock()
        sim.entity_id = uuid4()
        circuit = MagicMock()
        circuit.root_circuit_id = uuid4()
        circuit.lifecycle_status = "disqualified"

        db_client.get_entity.side_effect = [sim, circuit]
        with pytest.raises(ApiError, match="not ready for simulation"):
            _check_circuit_is_active(db_client, uuid4())

    def test_non_customized_circuit_passes(self):
        """Circuit without root_circuit_id (not customized) should pass."""
        db_client = MagicMock()
        sim = MagicMock()
        sim.entity_id = uuid4()
        circuit = MagicMock()
        circuit.root_circuit_id = None  # not a customized circuit

        db_client.get_entity.side_effect = [sim, circuit]
        _check_circuit_is_active(db_client, uuid4())  # should not raise

    def test_entity_not_found_passes(self):
        """If simulation or circuit can't be fetched, gate is skipped."""
        db_client = MagicMock()
        db_client.get_entity.side_effect = EntitySDKError("not found")
        _check_circuit_is_active(db_client, uuid4())  # should not raise

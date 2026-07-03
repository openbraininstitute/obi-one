"""Tests for the subject registration endpoint."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from entitysdk.models import Species

from app.application import app
from app.dependencies.entitysdk import get_client

_BASE = "/declared/subject"


def _make_mock_db_client(existing=None):
    mock_client = MagicMock()
    mock_search_result = MagicMock()
    mock_search_result.one_or_none.return_value = existing
    mock_client.search_entity.return_value = mock_search_result
    return mock_client


@pytest.fixture
def mock_db_client():
    return _make_mock_db_client()


@pytest.fixture(autouse=True)
def _override_db_client(mock_db_client, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_client, lambda: mock_db_client)
    yield
    app.dependency_overrides.pop(get_client, None)


VALID_SUBJECT = {
    "name": "Mouse_01",
    "description": "Adult male C57BL/6 mouse",
    "species_id": str(uuid4()),
    "sex": "male",
}


class TestGetSubject:
    def test_found(self, client, mock_db_client):
        """GET returns subject when found by name."""
        existing = MagicMock()
        existing.model_dump.return_value = {
            "id": str(uuid4()),
            "name": "Mouse_01",
            "description": "A mouse",
            "sex": "male",
        }
        mock_db_client.search_entity.return_value.one_or_none.return_value = existing

        resp = client.get(f"{_BASE}?name=Mouse_01")

        assert resp.status_code == 200
        assert resp.json()["name"] == "Mouse_01"

    def test_not_found(self, client):
        """GET returns 404 when subject not found."""
        resp = client.get(f"{_BASE}?name=NonExistent")

        assert resp.status_code == 404

    def test_unauthenticated(self, client_no_auth):
        resp = client_no_auth.get(f"{_BASE}?name=Mouse_01")
        assert resp.status_code in {401, 403}


class TestRegisterSubject:
    def test_register_new_subject(self, client, mock_db_client):
        """POST creates a new subject."""
        mock_db_client.get_entity.return_value = Species(
            id=uuid4(), name="Mus musculus", taxonomy_id="10090"
        )

        mock_registered = MagicMock()
        mock_registered.model_dump.return_value = {
            "id": str(uuid4()),
            "name": "Mouse_01",
            "description": "Adult male C57BL/6 mouse",
            "sex": "male",
        }
        mock_db_client.register_entity.return_value = mock_registered

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 201
        assert resp.json()["name"] == "Mouse_01"
        mock_db_client.register_entity.assert_called_once()

    def test_duplicate_name_returns_409(self, client, mock_db_client):
        """POST returns 409 when name already exists."""
        existing = MagicMock()
        existing.id = uuid4()
        mock_db_client.search_entity.return_value.one_or_none.return_value = existing

        resp = client.post(f"{_BASE}", json=VALID_SUBJECT)

        assert resp.status_code == 409
        assert "already exists" in resp.json()["message"]
        mock_db_client.register_entity.assert_not_called()

    def test_missing_required_fields(self, client):
        """POST with missing fields returns 422."""
        resp = client.post(f"{_BASE}", json={"name": "Mouse_01"})
        assert resp.status_code == 422

    def test_invalid_sex(self, client):
        """POST with invalid sex value returns 422."""
        data = {**VALID_SUBJECT, "sex": "invalid_value"}
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422

    def test_age_period_required_with_age_value(self, client):
        """POST with age_value but no age_period returns 422."""
        data = {**VALID_SUBJECT, "age_value": 86400}  # 1 day in seconds
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422

    def test_age_value_and_range_conflict(self, client):
        """POST with both age_value and age_min returns 422."""
        data = {
            **VALID_SUBJECT,
            "age_value": 86400,
            "age_min": 43200,
            "age_max": 172800,
            "age_period": "postnatal",
        }
        resp = client.post(f"{_BASE}", json=data)
        assert resp.status_code == 422

    def test_unauthenticated(self, client_no_auth):
        resp = client_no_auth.post(f"{_BASE}", json=VALID_SUBJECT)
        assert resp.status_code in {401, 403}

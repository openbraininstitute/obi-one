"""Tests for the contributor registration endpoint."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.application import app
from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.services.contributor_metadata import OrcidMetadata, RorMetadata

_BASE = "/declared/contributor"

VALID_ORCID = "0000-0000-1234-5672"
VALID_ROR = "00tsmxy07"

ORCID_METADATA = OrcidMetadata(
    orcid=VALID_ORCID,
    given_name="Jane",
    family_name="Doe",
    pref_label="Jane Doe",
)

ROR_METADATA = RorMetadata(
    ror_id=VALID_ROR,
    name="Open Brain Institute",
    alternative_names=["Open Brain Platform", "OBI"],
    types=["Nonprofit"],
    country="Switzerland",
)


def _make_mock_db_client(existing_entities=None):
    mock_client = MagicMock()
    mock_search_result = MagicMock()
    mock_search_result.one_or_none.return_value = (
        existing_entities[0] if existing_entities else None
    )
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


class TestContributorValidation:
    def test_invalid_identifier(self, client):
        """GET with invalid identifier returns 422."""
        resp = client.get(f"{_BASE}?identifier=not-valid-id")
        assert resp.status_code == 422

    def test_unauthenticated_get(self, client_no_auth):
        resp = client_no_auth.get(f"{_BASE}?identifier={VALID_ORCID}")
        assert resp.status_code in {401, 403}

    def test_unauthenticated_post(self, client_no_auth):
        resp = client_no_auth.post(f"{_BASE}?identifier={VALID_ORCID}")
        assert resp.status_code in {401, 403}


class TestGetContributorOrcid:
    def test_new_person_preview(self, client):
        """GET for ORCID not in DB returns preview."""
        with patch(
            "app.endpoints.contributor.fetch_orcid_metadata",
            return_value=ORCID_METADATA,
        ):
            resp = client.get(f"{_BASE}?identifier={VALID_ORCID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["identifier"] == VALID_ORCID
        assert data["identifier_type"] == "orcid"
        assert data["name"] == "Jane Doe"
        assert data["given_name"] == "Jane"
        assert data["family_name"] == "Doe"
        assert data["agent_type"] == "person"
        assert data["orcid"] == VALID_ORCID
        assert data["already_registered"] is False

    def test_existing_person(self, client, mock_db_client):
        """GET for ORCID already in DB returns already_registered=True."""
        existing = MagicMock()
        existing.id = uuid4()
        mock_db_client.search_entity.return_value.one_or_none.return_value = existing

        with patch(
            "app.endpoints.contributor.fetch_orcid_metadata",
            return_value=ORCID_METADATA,
        ):
            resp = client.get(f"{_BASE}?identifier={VALID_ORCID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["already_registered"] is True
        assert data["existing_id"] == str(existing.id)

    def test_orcid_not_found(self, client):
        """GET when ORCID API returns 404."""
        with patch(
            "app.endpoints.contributor.fetch_orcid_metadata",
            side_effect=ApiError(
                message="ORCID not found",
                error_code=ApiErrorCode.NOT_FOUND,
                http_status_code=404,
            ),
        ):
            resp = client.get(f"{_BASE}?identifier={VALID_ORCID}")

        assert resp.status_code == 404


class TestGetContributorRor:
    def test_new_organization_preview(self, client):
        """GET for ROR not in DB returns preview."""
        with patch(
            "app.endpoints.contributor.fetch_ror_metadata",
            return_value=ROR_METADATA,
        ):
            resp = client.get(f"{_BASE}?identifier={VALID_ROR}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["identifier"] == VALID_ROR
        assert data["identifier_type"] == "ror"
        assert data["name"] == "Open Brain Institute"
        assert data["alternative_name"] == "Open Brain Platform"
        assert data["agent_type"] == "organization"
        assert data["ror_id"] == VALID_ROR
        assert data["already_registered"] is False

    def test_existing_organization(self, client, mock_db_client):
        """GET for ROR already in DB returns already_registered=True."""
        existing = MagicMock()
        existing.id = uuid4()
        mock_db_client.search_entity.return_value.one_or_none.return_value = existing

        with patch(
            "app.endpoints.contributor.fetch_ror_metadata",
            return_value=ROR_METADATA,
        ):
            resp = client.get(f"{_BASE}?identifier={VALID_ROR}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["already_registered"] is True
        assert data["existing_id"] == str(existing.id)


class TestRegisterContributorOrcid:
    def test_register_new_person(self, client, mock_db_client):
        """POST for new ORCID registers a person."""
        mock_registered = MagicMock()
        mock_registered.model_dump.return_value = {
            "id": str(uuid4()),
            "type": "person",
            "pref_label": "Jane Doe",
            "given_name": "Jane",
            "family_name": "Doe",
        }
        mock_db_client.register_entity.return_value = mock_registered

        with patch(
            "app.endpoints.contributor.fetch_orcid_metadata",
            return_value=ORCID_METADATA,
        ):
            resp = client.post(f"{_BASE}?identifier={VALID_ORCID}")

        assert resp.status_code == 201
        data = resp.json()
        assert data["pref_label"] == "Jane Doe"
        mock_db_client.register_entity.assert_called_once()

    def test_register_existing_person_returns_409(self, client, mock_db_client):
        """POST for existing ORCID returns 409."""
        existing = MagicMock()
        existing.id = uuid4()
        mock_db_client.search_entity.return_value.one_or_none.return_value = existing

        with patch(
            "app.endpoints.contributor.fetch_orcid_metadata",
            return_value=ORCID_METADATA,
        ):
            resp = client.post(f"{_BASE}?identifier={VALID_ORCID}")

        assert resp.status_code == 409
        assert "already registered" in resp.json()["message"]
        mock_db_client.register_entity.assert_not_called()


class TestRegisterContributorRor:
    def test_register_new_organization(self, client, mock_db_client):
        """POST for new ROR registers an organization."""
        mock_registered = MagicMock()
        mock_registered.model_dump.return_value = {
            "id": str(uuid4()),
            "type": "organization",
            "pref_label": "Open Brain Institute",
            "alternative_name": "Open Brain Platform",
        }
        mock_db_client.register_entity.return_value = mock_registered

        with patch(
            "app.endpoints.contributor.fetch_ror_metadata",
            return_value=ROR_METADATA,
        ):
            resp = client.post(f"{_BASE}?identifier={VALID_ROR}")

        assert resp.status_code == 201
        data = resp.json()
        assert data["pref_label"] == "Open Brain Institute"
        mock_db_client.register_entity.assert_called_once()

    def test_register_existing_org_returns_409(self, client, mock_db_client):
        """POST for existing ROR returns 409."""
        existing = MagicMock()
        existing.id = uuid4()
        mock_db_client.search_entity.return_value.one_or_none.return_value = existing

        with patch(
            "app.endpoints.contributor.fetch_ror_metadata",
            return_value=ROR_METADATA,
        ):
            resp = client.post(f"{_BASE}?identifier={VALID_ROR}")

        assert resp.status_code == 409
        mock_db_client.register_entity.assert_not_called()

    def test_ror_api_unavailable(self, client):
        """POST when ROR API is down returns 502."""
        with patch(
            "app.endpoints.contributor.fetch_ror_metadata",
            side_effect=ApiError(
                message="Failed to connect to ROR API",
                error_code=ApiErrorCode.GENERIC_ERROR,
                http_status_code=502,
            ),
        ):
            resp = client.post(f"{_BASE}?identifier={VALID_ROR}")

        assert resp.status_code == 502

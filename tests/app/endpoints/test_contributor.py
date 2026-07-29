"""Tests for the contributor registration endpoint."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from entitysdk import models

from app.application import app
from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.schemas.contributor import OrcidMetadata, RorMetadata
from app.schemas.persistent_identifier import ORCID_URL_PREFIX, ROR_URL_PREFIX

_BASE = "/declared/contributor"

VALID_ORCID = "0000-0000-1234-5672"
VALID_ORCID_URL = f"{ORCID_URL_PREFIX}{VALID_ORCID}"
VALID_ROR = "00tsmxy07"
VALID_ROR_URL = f"{ROR_URL_PREFIX}{VALID_ROR}"

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

ROR_METADATA_NO_ALT = RorMetadata(
    ror_id=VALID_ROR,
    name="Open Brain Institute",
    alternative_names=[],
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


def test_invalid_identifier(client):
    resp = client.get(f"{_BASE}?identifier=not-valid-id")
    assert resp.status_code == 422


def test_unauthenticated_get(client_no_auth):
    resp = client_no_auth.get(f"{_BASE}?identifier={VALID_ORCID_URL}")
    assert resp.status_code in {401, 403}


def test_unauthenticated_post(client_no_auth):
    resp = client_no_auth.post(f"{_BASE}?identifier={VALID_ORCID_URL}")
    assert resp.status_code in {401, 403}


def test_get_new_person_preview(client):
    with patch(
        "app.endpoints.contributor.fetch_orcid_metadata",
        return_value=ORCID_METADATA,
    ):
        resp = client.get(f"{_BASE}?identifier={VALID_ORCID_URL}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["identifier"] == VALID_ORCID_URL
    assert data["identifier_type"] == "orcid"
    assert data["name"] == "Jane Doe"
    assert data["given_name"] == "Jane"
    assert data["family_name"] == "Doe"
    assert data["agent_type"] == "person"
    assert data["orcid"] == VALID_ORCID_URL
    assert data["already_registered"] is False


def test_get_existing_person(client, mock_db_client):
    existing = MagicMock()
    existing.id = uuid4()
    mock_db_client.search_entity.return_value.one_or_none.return_value = existing

    with patch(
        "app.endpoints.contributor.fetch_orcid_metadata",
        return_value=ORCID_METADATA,
    ):
        resp = client.get(f"{_BASE}?identifier={VALID_ORCID_URL}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["already_registered"] is True
    assert data["existing_id"] == str(existing.id)


def test_get_orcid_not_found(client):
    with patch(
        "app.endpoints.contributor.fetch_orcid_metadata",
        side_effect=ApiError(
            message="ORCID not found",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=404,
        ),
    ):
        resp = client.get(f"{_BASE}?identifier={VALID_ORCID_URL}")

    assert resp.status_code == 404


def test_get_new_organization_preview(client):
    with patch(
        "app.endpoints.contributor.fetch_ror_metadata",
        return_value=ROR_METADATA,
    ):
        resp = client.get(f"{_BASE}?identifier={VALID_ROR_URL}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["identifier"] == VALID_ROR_URL
    assert data["identifier_type"] == "ror"
    assert data["name"] == "Open Brain Institute"
    assert data["alternative_name"] == "Open Brain Platform"
    assert data["agent_type"] == "organization"
    assert data["ror_id"] == VALID_ROR_URL
    assert data["already_registered"] is False


def test_get_organization_without_alternative_name(client):
    with patch(
        "app.endpoints.contributor.fetch_ror_metadata",
        return_value=ROR_METADATA_NO_ALT,
    ):
        resp = client.get(f"{_BASE}?identifier={VALID_ROR_URL}")

    assert resp.status_code == 200
    assert resp.json()["alternative_name"] is None


def test_get_existing_organization(client, mock_db_client):
    existing = MagicMock()
    existing.id = uuid4()
    mock_db_client.search_entity.return_value.one_or_none.return_value = existing

    with patch(
        "app.endpoints.contributor.fetch_ror_metadata",
        return_value=ROR_METADATA,
    ):
        resp = client.get(f"{_BASE}?identifier={VALID_ROR_URL}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["already_registered"] is True
    assert data["existing_id"] == str(existing.id)


def test_register_new_person(client, mock_db_client):
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
        resp = client.post(f"{_BASE}?identifier={VALID_ORCID_URL}")

    assert resp.status_code == 201
    data = resp.json()
    assert data["pref_label"] == "Jane Doe"
    mock_db_client.register_entity.assert_called_once()
    registered_entity = mock_db_client.register_entity.call_args.kwargs["entity"]
    assert registered_entity.orcid == VALID_ORCID_URL
    mock_db_client.search_entity.assert_called_once_with(
        entity_type=models.Person,
        query={"orcid": VALID_ORCID_URL},
    )


def test_register_existing_person_returns_409(client, mock_db_client):
    existing = MagicMock()
    existing.id = uuid4()
    mock_db_client.search_entity.return_value.one_or_none.return_value = existing

    with patch(
        "app.endpoints.contributor.fetch_orcid_metadata",
        return_value=ORCID_METADATA,
    ):
        resp = client.post(f"{_BASE}?identifier={VALID_ORCID_URL}")

    assert resp.status_code == 409
    assert "already registered" in resp.json()["message"]
    mock_db_client.register_entity.assert_not_called()


def test_register_new_organization(client, mock_db_client):
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
        resp = client.post(f"{_BASE}?identifier={VALID_ROR_URL}")

    assert resp.status_code == 201
    data = resp.json()
    assert data["pref_label"] == "Open Brain Institute"
    mock_db_client.register_entity.assert_called_once()


def test_register_organization_without_alternative_name(client, mock_db_client):
    mock_registered = MagicMock()
    mock_registered.model_dump.return_value = {
        "id": str(uuid4()),
        "type": "organization",
        "pref_label": "Open Brain Institute",
    }
    mock_db_client.register_entity.return_value = mock_registered

    with patch(
        "app.endpoints.contributor.fetch_ror_metadata",
        return_value=ROR_METADATA_NO_ALT,
    ):
        resp = client.post(f"{_BASE}?identifier={VALID_ROR_URL}")

    assert resp.status_code == 201
    registered_entity = mock_db_client.register_entity.call_args.kwargs["entity"]
    assert registered_entity.alternative_name is None


def test_register_existing_org_returns_409(client, mock_db_client):
    existing = MagicMock()
    existing.id = uuid4()
    mock_db_client.search_entity.return_value.one_or_none.return_value = existing

    with patch(
        "app.endpoints.contributor.fetch_ror_metadata",
        return_value=ROR_METADATA,
    ):
        resp = client.post(f"{_BASE}?identifier={VALID_ROR_URL}")

    assert resp.status_code == 409
    mock_db_client.register_entity.assert_not_called()


def test_register_ror_api_unavailable(client):
    with patch(
        "app.endpoints.contributor.fetch_ror_metadata",
        side_effect=ApiError(
            message="Failed to connect to ROR API",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=502,
        ),
    ):
        resp = client.post(f"{_BASE}?identifier={VALID_ROR_URL}")

    assert resp.status_code == 502

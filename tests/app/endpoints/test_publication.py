"""Tests for the publication registration endpoint."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.application import app
from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode

_BASE = "/declared/publication"

VALID_DOI = "10.1038/nature12345"

CROSSREF_METADATA = {
    "DOI": VALID_DOI,
    "title": "Groundbreaking research",
    "authors": [
        {"given_name": "J.", "family_name": "Parker"},
        {"given_name": "A. C.", "family_name": "Smith"},
    ],
    "publication_year": 2025,
    "abstract": "We describe a new groundbreaking research.",
}


def _mock_registered_publication():
    """Return a mock registered publication entity with model_dump."""
    pub = MagicMock()
    pub.id = uuid4()
    pub.DOI = VALID_DOI
    pub.title = CROSSREF_METADATA["title"]
    pub.authors = CROSSREF_METADATA["authors"]
    pub.publication_year = CROSSREF_METADATA["publication_year"]
    pub.abstract = CROSSREF_METADATA["abstract"]
    pub.model_dump.return_value = {
        "id": str(pub.id),
        "DOI": pub.DOI,
        "title": pub.title,
        "authors": pub.authors,
        "publication_year": pub.publication_year,
        "abstract": pub.abstract,
    }
    return pub


def _make_mock_db_client(existing_publications=None):
    """Create a mock entitysdk client."""
    mock_client = MagicMock()
    mock_search_result = MagicMock()
    mock_search_result.all.return_value = existing_publications or []
    mock_client.search_entity.return_value = mock_search_result
    return mock_client


@pytest.fixture
def mock_db_client():
    return _make_mock_db_client()


@pytest.fixture(autouse=True)
def _override_db_client(mock_db_client, monkeypatch):
    """Override the DatabaseClientDep with a mock for all tests in this module."""
    monkeypatch.setitem(app.dependency_overrides, get_client, lambda: mock_db_client)
    yield
    app.dependency_overrides.pop(get_client, None)


class TestPublicationValidation:
    def test_invalid_doi_format(self, client):
        """POST with an invalid DOI returns 422 validation error."""
        resp = client.post(f"{_BASE}/register", json={"DOI": "not-a-doi"})
        assert resp.status_code == 422

    def test_missing_doi_field(self, client):
        """POST without DOI field returns 422 validation error."""
        resp = client.post(f"{_BASE}/register", json={})
        assert resp.status_code == 422

    def test_empty_doi(self, client):
        """POST with empty DOI returns 422 validation error."""
        resp = client.post(f"{_BASE}/register", json={"DOI": ""})
        assert resp.status_code == 422

    def test_unauthenticated(self, client_no_auth):
        """POST without auth headers returns 401 or 403."""
        resp = client_no_auth.post(f"{_BASE}/register", json={"DOI": VALID_DOI})
        assert resp.status_code in {401, 403}


class TestRegisterPublicationSuccess:
    def test_registers_new_publication(self, client, mock_db_client):
        """A new DOI is looked up on Crossref and registered in entitycore."""
        mock_pub = _mock_registered_publication()
        mock_db_client.register_entity.return_value = mock_pub

        with patch(
            "app.endpoints.publication.fetch_publication_metadata",
            return_value=CROSSREF_METADATA,
        ) as mock_fetch:
            resp = client.post(f"{_BASE}/register", json={"DOI": VALID_DOI})

        assert resp.status_code == 200
        data = resp.json()
        assert data["DOI"] == VALID_DOI
        assert data["title"] == CROSSREF_METADATA["title"]
        assert data["publication_year"] == CROSSREF_METADATA["publication_year"]
        assert len(data["authors"]) == len(CROSSREF_METADATA["authors"])

        mock_fetch.assert_called_once()
        mock_db_client.search_entity.assert_called_once()
        mock_db_client.register_entity.assert_called_once()


class TestRegisterPublicationAlreadyExists:
    def test_already_registered_returns_409(self, client, mock_db_client):
        """A DOI that already exists returns 409 Conflict."""
        existing_pub = MagicMock()
        mock_db_client.search_entity.return_value.all.return_value = [existing_pub]

        resp = client.post(f"{_BASE}/register", json={"DOI": VALID_DOI})

        assert resp.status_code == 409
        data = resp.json()
        assert "already registered" in data["message"]
        mock_db_client.register_entity.assert_not_called()


class TestRegisterPublicationCrossrefErrors:
    def test_crossref_not_found_returns_404(self, client, mock_db_client):
        """A DOI not found on Crossref returns 404."""
        with patch(
            "app.endpoints.publication.fetch_publication_metadata",
            side_effect=ApiError(
                message="DOI not found in Crossref: 10.1234/missing",
                error_code=ApiErrorCode.INVALID_REQUEST,
                http_status_code=404,
            ),
        ):
            resp = client.post(f"{_BASE}/register", json={"DOI": "10.1234/missing"})

        assert resp.status_code == 404
        mock_db_client.register_entity.assert_not_called()

    def test_crossref_unavailable_returns_502(self, client, mock_db_client):
        """Crossref API being down returns 502."""
        with patch(
            "app.endpoints.publication.fetch_publication_metadata",
            side_effect=ApiError(
                message="Failed to connect to Crossref API",
                error_code=ApiErrorCode.GENERIC_ERROR,
                http_status_code=502,
            ),
        ):
            resp = client.post(f"{_BASE}/register", json={"DOI": VALID_DOI})

        assert resp.status_code == 502
        mock_db_client.register_entity.assert_not_called()

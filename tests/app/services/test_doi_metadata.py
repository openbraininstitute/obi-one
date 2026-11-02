"""Tests for app.services.doi_metadata — DOI metadata fetching."""

import json
from http import HTTPStatus
from unittest.mock import MagicMock

import httpx
import pytest

from app.errors import ApiError, ApiErrorCode
from app.services.doi_metadata import (
    _extract_authors,
    _extract_publication_year,
    fetch_publication_metadata,
)

DOI = "10.1038/nature12345"

CROSSREF_RESPONSE_JSON = {
    "status": "ok",
    "message-type": "work",
    "message": {
        "DOI": DOI,
        "title": ["Groundbreaking research"],
        "author": [
            {"given": "J.", "family": "Parker", "sequence": "first"},
            {"given": "A. C.", "family": "Smith", "sequence": "additional"},
        ],
        "published-print": {"date-parts": [[2025, 1]]},
        "published-online": {"date-parts": [[2025, 1, 7]]},
        "abstract": "<p>We describe a new groundbreaking research.</p>",
    },
}


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    """Build a real httpx.Response."""
    content = json.dumps(json_data or {}).encode()
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": "application/json"},
    )


class TestFetchPublicationMetadata:
    def test_success(self):
        """Metadata is correctly extracted from a successful Crossref response."""
        http_client = MagicMock()
        http_client.request.return_value = _make_response(200, CROSSREF_RESPONSE_JSON)

        result = fetch_publication_metadata(doi=DOI, http_client=http_client)

        assert result["DOI"] == DOI
        assert result["title"] == "Groundbreaking research"
        assert len(result["authors"]) == 2
        assert result["authors"][0] == {"given_name": "J.", "family_name": "Parker"}
        assert result["authors"][1] == {"given_name": "A. C.", "family_name": "Smith"}
        assert result["publication_year"] == 2025
        assert "groundbreaking" in result["abstract"]

    def test_doi_not_found(self):
        """A 404 from Crossref raises ApiError with NOT_FOUND status."""
        http_client = MagicMock()
        http_client.request.return_value = _make_response(404, {"message": "not found"})

        with pytest.raises(ApiError) as exc_info:
            fetch_publication_metadata(doi="10.1234/nonexistent", http_client=http_client)

        assert exc_info.value.http_status_code == HTTPStatus.NOT_FOUND
        assert exc_info.value.error_code == ApiErrorCode.INVALID_REQUEST

    def test_server_error(self):
        """A 500 from Crossref raises ApiError with BAD_GATEWAY status."""
        http_client = MagicMock()
        http_client.request.return_value = _make_response(500, {})

        with pytest.raises(ApiError) as exc_info:
            fetch_publication_metadata(doi=DOI, http_client=http_client)

        assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY

    def test_connection_error(self):
        """A network error raises ApiError with BAD_GATEWAY status."""
        http_client = MagicMock()
        http_client.request.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(ApiError) as exc_info:
            fetch_publication_metadata(doi=DOI, http_client=http_client)

        assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY

    def test_missing_optional_fields(self):
        """Missing title, authors, year, and abstract return None."""
        minimal_response = {
            "status": "ok",
            "message": {"DOI": DOI},
        }
        http_client = MagicMock()
        http_client.request.return_value = _make_response(200, minimal_response)

        result = fetch_publication_metadata(doi=DOI, http_client=http_client)

        assert result["DOI"] == DOI
        assert result["title"] is None
        assert result["authors"] is None
        assert result["publication_year"] is None
        assert result["abstract"] is None


class TestExtractAuthors:
    def test_standard_authors(self):
        raw = [
            {"given": "Alice", "family": "Scott"},
            {"given": "Bob", "family": "Jones"},
        ]
        result = _extract_authors(raw)
        assert result == [
            {"given_name": "Alice", "family_name": "Scott"},
            {"given_name": "Bob", "family_name": "Jones"},
        ]

    def test_missing_given_name(self):
        """Authors with only family name are still included."""
        raw = [{"family": "Consortium"}]
        result = _extract_authors(raw)
        assert result == [{"given_name": "", "family_name": "Consortium"}]

    def test_empty_list(self):
        assert _extract_authors([]) == []

    def test_entries_without_names_are_skipped(self):
        """Entries with neither given nor family are skipped."""
        raw = [{"sequence": "first", "affiliation": []}]
        result = _extract_authors(raw)
        assert result == []


class TestExtractPublicationYear:
    def test_published_print_preferred(self):
        message = {
            "published-print": {"date-parts": [[2020, 10]]},
            "published-online": {"date-parts": [[2020, 10, 22]]},
        }
        assert _extract_publication_year(message) == 2020

    def test_falls_back_to_published_online(self):
        message = {"published-online": {"date-parts": [[2023, 8, 18]]}}
        assert _extract_publication_year(message) == 2023

    def test_falls_back_to_issued(self):
        message = {"issued": {"date-parts": [[2017]]}}
        assert _extract_publication_year(message) == 2017

    def test_returns_none_when_no_dates(self):
        assert _extract_publication_year({}) is None

    def test_returns_none_for_empty_date_parts(self):
        message = {"published-print": {"date-parts": [[]]}}
        assert _extract_publication_year(message) is None

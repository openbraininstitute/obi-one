"""Tests for app.services.contributor_metadata — ORCID and ROR metadata fetching."""

import json
from http import HTTPStatus
from unittest.mock import MagicMock

import httpx
import pytest

from app.errors import ApiError
from app.services.contributor_metadata import (
    IdentifierType,
    fetch_orcid_metadata,
    fetch_ror_metadata,
    resolve_identifier,
)


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    content = json.dumps(json_data or {}).encode()
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": "application/json"},
    )


class TestResolveIdentifierType:
    def test_valid_orcid(self):
        id_type, _ = resolve_identifier("0000-0000-1234-5672")
        assert id_type == IdentifierType.orcid

    def test_valid_orcid_with_x(self):
        id_type, _ = resolve_identifier("0000-0001-5109-325X")
        assert id_type == IdentifierType.orcid

    def test_valid_ror_bare(self):
        id_type, _ = resolve_identifier("00tsmxy07")
        assert id_type == IdentifierType.ror

    def test_valid_ror_url(self):
        id_type, _ = resolve_identifier("https://ror.org/00tsmxy07")
        assert id_type == IdentifierType.ror

    def test_invalid_identifier(self):
        with pytest.raises(ApiError) as exc_info:
            resolve_identifier("not-a-valid-id")
        assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    def test_empty_string(self):
        with pytest.raises(ApiError):
            resolve_identifier("")

    def test_partial_orcid(self):
        with pytest.raises(ApiError):
            resolve_identifier("0000-0002-1825")

    def test_invalid_orcid_checksum(self):
        """ORCID with wrong check digit is rejected."""
        with pytest.raises(ApiError) as exc_info:
            resolve_identifier("0000-0002-1825-0098")  # wrong last digit
        assert "checksum" in exc_info.value.message.lower()

    def test_invalid_ror_checksum(self):
        """ROR with wrong check digits is rejected."""
        with pytest.raises(ApiError) as exc_info:
            resolve_identifier("03yrm5c99")  # wrong check digits
        assert "checksum" in exc_info.value.message.lower()


class TestResolveIdentifier:
    def test_bare_ror_unchanged(self):
        id_type, normalized = resolve_identifier("00tsmxy07")
        assert id_type == IdentifierType.ror
        assert normalized == "00tsmxy07"

    def test_ror_url_stripped(self):
        id_type, normalized = resolve_identifier("https://ror.org/00tsmxy07")
        assert id_type == IdentifierType.ror
        assert normalized == "00tsmxy07"

    def test_ror_http_url_stripped(self):
        id_type, normalized = resolve_identifier("http://ror.org/00tsmxy07")
        assert id_type == IdentifierType.ror
        assert normalized == "00tsmxy07"

    def test_bare_orcid_unchanged(self):
        id_type, normalized = resolve_identifier("0000-0000-1234-5672")
        assert id_type == IdentifierType.orcid
        assert normalized == "0000-0000-1234-5672"

    def test_orcid_url_stripped(self):
        id_type, normalized = resolve_identifier("https://orcid.org/0000-0000-1234-5672")
        assert id_type == IdentifierType.orcid
        assert normalized == "0000-0000-1234-5672"


ORCID_RESPONSE = {
    "person": {
        "name": {
            "given-names": {"value": "Jane"},
            "family-name": {"value": "Doe"},
            "credit-name": None,
        }
    }
}

ORCID_RESPONSE_CREDIT_NAME = {
    "person": {
        "name": {
            "given-names": {"value": "J."},
            "family-name": {"value": "Doe"},
            "credit-name": {"value": "Jane S. Doe"},
        }
    }
}


class TestFetchOrcidMetadata:
    def test_success(self):
        http_client = MagicMock()
        http_client.request.return_value = _make_response(200, ORCID_RESPONSE)

        result = fetch_orcid_metadata(orcid="0000-0000-1234-5672", http_client=http_client)

        assert result.orcid == "0000-0000-1234-5672"
        assert result.given_name == "Jane"
        assert result.family_name == "Doe"
        assert result.pref_label == "Jane Doe"

    def test_credit_name_preferred(self):
        http_client = MagicMock()
        http_client.request.return_value = _make_response(200, ORCID_RESPONSE_CREDIT_NAME)

        result = fetch_orcid_metadata(orcid="0000-0000-1234-5672", http_client=http_client)

        assert result.pref_label == "Jane S. Doe"

    def test_not_found(self):
        http_client = MagicMock()
        http_client.request.return_value = _make_response(404)

        with pytest.raises(ApiError) as exc_info:
            fetch_orcid_metadata(orcid="0000-0000-0000-0000", http_client=http_client)
        assert exc_info.value.http_status_code == HTTPStatus.NOT_FOUND

    def test_server_error(self):
        http_client = MagicMock()
        http_client.request.return_value = _make_response(500)

        with pytest.raises(ApiError) as exc_info:
            fetch_orcid_metadata(orcid="0000-0000-1234-5672", http_client=http_client)
        assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY

    def test_connection_error(self):
        http_client = MagicMock()
        http_client.request.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ApiError) as exc_info:
            fetch_orcid_metadata(orcid="0000-0000-1234-5672", http_client=http_client)
        assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY

    def test_missing_name_fields(self):
        """When name info is empty, pref_label falls back to ORCID."""
        http_client = MagicMock()
        http_client.request.return_value = _make_response(200, {"person": {"name": None}})

        result = fetch_orcid_metadata(orcid="0000-0000-1234-5672", http_client=http_client)

        assert result.pref_label == "0000-0000-1234-5672"
        assert result.given_name is None
        assert result.family_name is None


ROR_RESPONSE = {
    "names": [
        {"value": "Open Brain Institute", "types": ["ror_display"]},
        {"value": "Open Brain Platform", "types": ["alias"]},
        {"value": "OBI", "types": ["alias"]},
    ],
    "types": ["Nonprofit"],
    "locations": [{"geonames_details": {"country_name": "Switzerland"}}],
}


class TestFetchRorMetadata:
    def test_success(self):
        http_client = MagicMock()
        http_client.request.return_value = _make_response(200, ROR_RESPONSE)

        result = fetch_ror_metadata(ror_id="00tsmxy07", http_client=http_client)

        assert result.ror_id == "00tsmxy07"
        assert result.name == "Open Brain Institute"
        assert result.alternative_names == ["Open Brain Platform", "OBI"]
        assert result.types == ["Nonprofit"]
        assert result.country == "Switzerland"

    def test_not_found(self):
        http_client = MagicMock()
        http_client.request.return_value = _make_response(404)

        with pytest.raises(ApiError) as exc_info:
            fetch_ror_metadata(ror_id="0000000000", http_client=http_client)
        assert exc_info.value.http_status_code == HTTPStatus.NOT_FOUND

    def test_server_error(self):
        http_client = MagicMock()
        http_client.request.return_value = _make_response(500)

        with pytest.raises(ApiError) as exc_info:
            fetch_ror_metadata(ror_id="00tsmxy07", http_client=http_client)
        assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY

    def test_connection_error(self):
        http_client = MagicMock()
        http_client.request.side_effect = httpx.ConnectError("refused")

        with pytest.raises(ApiError) as exc_info:
            fetch_ror_metadata(ror_id="00tsmxy07", http_client=http_client)
        assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY

    def test_no_ror_display_name(self):
        """Falls back to first name entry when no ror_display type."""
        response_data = {
            "names": [{"value": "Some Org", "types": ["label"]}],
            "types": [],
            "locations": [],
        }
        http_client = MagicMock()
        http_client.request.return_value = _make_response(200, response_data)

        result = fetch_ror_metadata(ror_id="00tsmxy07", http_client=http_client)

        assert result.name == "Some Org"
        assert result.country is None

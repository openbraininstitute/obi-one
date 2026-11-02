"""Tests for app.services.contributor — ORCID and ROR metadata fetching."""

import json
from http import HTTPStatus
from unittest.mock import MagicMock

import httpx
import pytest

from app.errors import ApiError
from app.schemas.persistent_identifier import (
    ORCID_URL_PREFIX,
    ROR_URL_PREFIX,
    OrcidPersistentIdentifier,
    RorPersistentIdentifier,
)
from app.services.contributor import fetch_orcid_metadata, fetch_ror_metadata
from app.types import IdentifierType

VALID_ORCID = "0000-0000-1234-5672"
VALID_ORCID_URL = f"{ORCID_URL_PREFIX}{VALID_ORCID}"
VALID_ROR = "00tsmxy07"
VALID_ROR_URL = f"{ROR_URL_PREFIX}{VALID_ROR}"


@pytest.fixture
def orcid_identifier():
    return OrcidPersistentIdentifier(kind=IdentifierType.orcid, url=VALID_ORCID_URL)


@pytest.fixture
def ror_identifier():
    return RorPersistentIdentifier(kind=IdentifierType.ror, url=VALID_ROR_URL)


def _make_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    content = json.dumps(json_data or {}).encode()
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"content-type": "application/json"},
    )


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


def test_fetch_orcid_metadata_success(orcid_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(200, ORCID_RESPONSE)

    result = fetch_orcid_metadata(identifier=orcid_identifier, http_client=http_client)

    assert result.orcid == VALID_ORCID
    assert result.given_name == "Jane"
    assert result.family_name == "Doe"
    assert result.pref_label == "Jane Doe"


def test_fetch_orcid_metadata_credit_name_preferred(orcid_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(200, ORCID_RESPONSE_CREDIT_NAME)

    result = fetch_orcid_metadata(identifier=orcid_identifier, http_client=http_client)

    assert result.pref_label == "Jane S. Doe"


def test_fetch_orcid_metadata_uses_id_in_request(orcid_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(200, ORCID_RESPONSE)

    fetch_orcid_metadata(identifier=orcid_identifier, http_client=http_client)

    http_client.request.assert_called_once()
    assert f"/{VALID_ORCID}/record" in http_client.request.call_args.kwargs["url"]


def test_fetch_orcid_metadata_not_found(orcid_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(404)

    with pytest.raises(ApiError) as exc_info:
        fetch_orcid_metadata(identifier=orcid_identifier, http_client=http_client)
    assert exc_info.value.http_status_code == HTTPStatus.NOT_FOUND


def test_fetch_orcid_metadata_server_error(orcid_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(500)

    with pytest.raises(ApiError) as exc_info:
        fetch_orcid_metadata(identifier=orcid_identifier, http_client=http_client)
    assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY


def test_fetch_orcid_metadata_connection_error(orcid_identifier):
    http_client = MagicMock()
    http_client.request.side_effect = httpx.ConnectError("refused")

    with pytest.raises(ApiError) as exc_info:
        fetch_orcid_metadata(identifier=orcid_identifier, http_client=http_client)
    assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY


def test_fetch_orcid_metadata_missing_name_fields(orcid_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(200, {"person": {"name": None}})

    result = fetch_orcid_metadata(identifier=orcid_identifier, http_client=http_client)

    assert result.pref_label == VALID_ORCID
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


def test_fetch_ror_metadata_success(ror_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(200, ROR_RESPONSE)

    result = fetch_ror_metadata(identifier=ror_identifier, http_client=http_client)

    assert result.ror_id == VALID_ROR
    assert result.name == "Open Brain Institute"
    assert result.alternative_names == ["Open Brain Platform", "OBI"]
    assert result.types == ["Nonprofit"]
    assert result.country == "Switzerland"


def test_fetch_ror_metadata_not_found(ror_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(404)

    with pytest.raises(ApiError) as exc_info:
        fetch_ror_metadata(identifier=ror_identifier, http_client=http_client)
    assert exc_info.value.http_status_code == HTTPStatus.NOT_FOUND


def test_fetch_ror_metadata_server_error(ror_identifier):
    http_client = MagicMock()
    http_client.request.return_value = _make_response(500)

    with pytest.raises(ApiError) as exc_info:
        fetch_ror_metadata(identifier=ror_identifier, http_client=http_client)
    assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY


def test_fetch_ror_metadata_connection_error(ror_identifier):
    http_client = MagicMock()
    http_client.request.side_effect = httpx.ConnectError("refused")

    with pytest.raises(ApiError) as exc_info:
        fetch_ror_metadata(identifier=ror_identifier, http_client=http_client)
    assert exc_info.value.http_status_code == HTTPStatus.BAD_GATEWAY


def test_fetch_ror_metadata_no_ror_display_name(ror_identifier):
    response_data = {
        "names": [{"value": "Some Org", "types": ["label"]}],
        "types": [],
        "locations": [],
    }
    http_client = MagicMock()
    http_client.request.return_value = _make_response(200, response_data)

    result = fetch_ror_metadata(identifier=ror_identifier, http_client=http_client)

    assert result.name == "Some Org"
    assert result.country is None

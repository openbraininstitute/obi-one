"""Tests for the persistent identifier FastAPI dependency."""

from http import HTTPStatus

import pytest

from app.dependencies.persistent_identifier import get_persistent_identifier
from app.errors import ApiError
from app.schemas.persistent_identifier import (
    ORCID_URL_PREFIX,
    ROR_URL_PREFIX,
    OrcidPersistentIdentifier,
    RorPersistentIdentifier,
)
from app.types import IdentifierType

VALID_ORCID = "0000-0000-1234-5672"
VALID_ORCID_URL = f"{ORCID_URL_PREFIX}{VALID_ORCID}"
VALID_ROR = "00tsmxy07"
VALID_ROR_URL = f"{ROR_URL_PREFIX}{VALID_ROR}"


def test_get_persistent_identifier_orcid_url():
    identifier = get_persistent_identifier(VALID_ORCID_URL)
    assert isinstance(identifier, OrcidPersistentIdentifier)
    assert identifier.kind == IdentifierType.orcid
    assert identifier.url == VALID_ORCID_URL
    assert identifier.id == VALID_ORCID


def test_get_persistent_identifier_ror_url():
    identifier = get_persistent_identifier(VALID_ROR_URL)
    assert isinstance(identifier, RorPersistentIdentifier)
    assert identifier.kind == IdentifierType.ror
    assert identifier.url == VALID_ROR_URL
    assert identifier.id == VALID_ROR


def test_get_persistent_identifier_rejects_orcid_without_url_prefix():
    with pytest.raises(ApiError) as exc_info:
        get_persistent_identifier(VALID_ORCID)
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_persistent_identifier_rejects_ror_without_url_prefix():
    with pytest.raises(ApiError) as exc_info:
        get_persistent_identifier(VALID_ROR)
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_persistent_identifier_rejects_invalid():
    with pytest.raises(ApiError) as exc_info:
        get_persistent_identifier("not-a-valid-id")
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_persistent_identifier_rejects_invalid_orcid_checksum():
    with pytest.raises(ApiError) as exc_info:
        get_persistent_identifier(f"{ORCID_URL_PREFIX}0000-0002-1825-0098")
    assert "checksum" in exc_info.value.message.lower()


def test_get_persistent_identifier_rejects_invalid_ror_checksum():
    with pytest.raises(ApiError) as exc_info:
        get_persistent_identifier(f"{ROR_URL_PREFIX}03yrm5c99")
    assert "checksum" in exc_info.value.message.lower()

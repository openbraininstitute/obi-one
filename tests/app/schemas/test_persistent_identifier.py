"""Tests for persistent identifier parsing and validation."""

import pytest

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


def test_orcid_persistent_identifier_id_property():
    identifier = OrcidPersistentIdentifier(kind=IdentifierType.orcid, url=VALID_ORCID_URL)
    assert identifier.id == VALID_ORCID


def test_ror_persistent_identifier_id_property():
    identifier = RorPersistentIdentifier(kind=IdentifierType.ror, url=VALID_ROR_URL)
    assert identifier.id == VALID_ROR


def test_orcid_url_invalid_format():
    with pytest.raises(ApiError) as exc_info:
        OrcidPersistentIdentifier(kind=IdentifierType.orcid, url="https://orcid.org/bad")
    assert "Invalid ORCID format" in exc_info.value.message


def test_orcid_url_invalid_checksum():
    with pytest.raises(ApiError) as exc_info:
        OrcidPersistentIdentifier(
            kind=IdentifierType.orcid,
            url=f"{ORCID_URL_PREFIX}0000-0002-1825-0098",
        )
    assert "checksum" in exc_info.value.message.lower()


def test_ror_url_invalid_checksum():
    with pytest.raises(ApiError) as exc_info:
        RorPersistentIdentifier(kind=IdentifierType.ror, url=f"{ROR_URL_PREFIX}03yrm5c99")
    assert "checksum" in exc_info.value.message.lower()


def test_ror_url_invalid_format():
    with pytest.raises(ApiError) as exc_info:
        RorPersistentIdentifier(kind=IdentifierType.ror, url="https://ror.org/badid")
    assert "Invalid ROR ID format" in exc_info.value.message


def test_orcid_url_rejects_missing_prefix():
    with pytest.raises(ApiError) as exc_info:
        OrcidPersistentIdentifier(kind=IdentifierType.orcid, url=VALID_ORCID)
    assert "Invalid ORCID URL" in exc_info.value.message


def test_ror_url_rejects_missing_prefix():
    with pytest.raises(ApiError) as exc_info:
        RorPersistentIdentifier(kind=IdentifierType.ror, url=VALID_ROR)
    assert "Invalid ROR URL" in exc_info.value.message

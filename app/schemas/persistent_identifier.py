import re
from http import HTTPStatus
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field

from app.errors import ApiError, ApiErrorCode
from app.schemas.base import Schema
from app.types import IdentifierType

ORCID_URL_PREFIX = "https://orcid.org/"
ROR_URL_PREFIX = "https://ror.org/"

ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
ROR_BARE_PATTERN = re.compile(r"^0[a-hj-km-np-tv-z0-9]{6}[0-9]{2}$")


def _validate_orcid_url(url: str) -> str:
    """Validate ORCID format and checksum, raising ApiError on failure."""
    bare = url.removeprefix(ORCID_URL_PREFIX)
    if not ORCID_PATTERN.match(bare):
        raise ApiError(
            message=f"Invalid ORCID format: '{url}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    if not _validate_orcid_checksum(bare):
        raise ApiError(
            message=f"Invalid ORCID checksum: '{url}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    return url


def _validate_orcid_checksum(orcid: str) -> bool:
    """Validate ORCID checksum using ISO 7064 Mod 11,2.

    The last character is the check digit (0-9 or X).
    """
    digits = orcid.replace("-", "")
    total = 0
    for char in digits[:-1]:
        total = (total + int(char)) * 2
    remainder = total % 11
    check = (12 - remainder) % 11
    expected = "X" if check == 10 else str(check)  # noqa: PLR2004
    return digits[-1] == expected


def _validate_ror_url(identifier: str) -> str:
    """Validate ROR ID format and checksum, raising ApiError on failure."""
    bare = identifier.removeprefix(ROR_URL_PREFIX)
    if not ROR_BARE_PATTERN.match(bare):
        raise ApiError(
            message=f"Invalid ROR ID format: '{identifier}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    if not _validate_ror_checksum(bare):
        raise ApiError(
            message=f"Invalid ROR ID checksum: '{identifier}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )


# Crockford Base32 alphabet (excludes I, L, O, U)
_CROCKFORD_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"


def _validate_ror_checksum(ror_id: str) -> bool:
    """Validate ROR ID checksum using ISO 7064 Mod 97-10.

    The ROR ID structure: 0 + 6 Crockford Base32 chars + 2 decimal check digits.
    To validate: decode the 6 Base32 chars to a number, append check digits, mod 97 == 1.
    """
    base32_chars = ror_id[1:7]  # 6 Crockford Base32 characters
    check_digits = ror_id[7:9]  # 2 decimal check digits

    # Decode Crockford Base32 to integer
    number = 0
    for char in base32_chars:
        idx = _CROCKFORD_ALPHABET.index(char)
        number = number * 32 + idx

    # Combine with check digits and validate mod 97
    combined = number * 100 + int(check_digits)
    return combined % 97 == 1


RorUrl = Annotated[str, BeforeValidator(_validate_ror_url)]
OrcidUrl = Annotated[str, BeforeValidator(_validate_orcid_url)]


class OrcidPersistentIdentifier(Schema):
    kind: Literal[IdentifierType.orcid]
    url: OrcidUrl

    @property
    def id(self) -> str:
        return self.url.removeprefix(ORCID_URL_PREFIX)


class RorPersistentIdentifier(Schema):
    kind: Literal[IdentifierType.ror]
    url: RorUrl

    @property
    def id(self) -> str:
        return self.url.removeprefix(ROR_URL_PREFIX)


type PersistentIdentifier = Annotated[
    OrcidPersistentIdentifier | RorPersistentIdentifier,
    Field(discriminator="kind"),
]

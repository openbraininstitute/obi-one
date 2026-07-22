"""Service for fetching contributor metadata from ORCID and ROR public APIs.

- ORCID Public API v3.0: https://pub.orcid.org
- ROR API v2: https://api.ror.org

To switch metadata providers, update the implementation in this module without
changing the public interface (fetch_orcid_metadata, fetch_ror_metadata).
"""

import re
from enum import StrEnum, auto
from http import HTTPStatus

import httpx
from pydantic import BaseModel

from app.errors import ApiError, ApiErrorCode
from app.logger import L

ORCID_API_BASE_URL = "https://pub.orcid.org/v3.0"
ROR_API_BASE_URL = "https://api.ror.org/v2/organizations"

ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
ROR_BARE_PATTERN = re.compile(r"^0[a-hj-km-np-tv-z0-9]{6}[0-9]{2}$")


class IdentifierType(StrEnum):
    orcid = auto()
    ror = auto()


class OrcidMetadata(BaseModel):
    """Metadata for a person fetched from the ORCID API."""

    orcid: str
    given_name: str | None = None
    family_name: str | None = None
    pref_label: str


class RorMetadata(BaseModel):
    """Metadata for an organization fetched from the ROR API."""

    ror_id: str
    name: str
    alternative_names: list[str] = []
    types: list[str] = []
    country: str | None = None


def resolve_identifier(identifier: str) -> tuple[IdentifierType, str]:
    """Validate, classify, and normalize an identifier in one step.

    Accepts bare identifiers or full URLs (https://orcid.org/... or https://ror.org/...).
    Returns the identifier type and the bare normalized form.
    Raises ApiError with 422 if the format is unrecognized or checksum is invalid.
    """
    stripped = identifier.strip()

    # URL forms: strip prefix and branch early
    if stripped.startswith("https://orcid.org/"):
        bare = stripped.rsplit("/", 1)[-1]
        _assert_valid_orcid(bare, identifier)
        return IdentifierType.orcid, bare

    if stripped.startswith(("https://ror.org/", "http://ror.org/")):
        bare = stripped.rsplit("/", 1)[-1]
        _assert_valid_ror(bare, identifier)
        return IdentifierType.ror, bare

    # Bare forms
    if ORCID_PATTERN.match(stripped):
        _assert_valid_orcid(stripped, identifier)
        return IdentifierType.orcid, stripped

    if ROR_BARE_PATTERN.match(stripped):
        _assert_valid_ror(stripped, identifier)
        return IdentifierType.ror, stripped

    raise ApiError(
        message=(
            f"Invalid identifier format: '{identifier}'. "
            "Expected ORCID (0000-0000-0000-000X with optional https://orcid.org/ prefix) "
            "or ROR ID (0xxxxxxxxx with optional https://ror.org/ prefix)."
        ),
        error_code=ApiErrorCode.INVALID_REQUEST,
        http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def _assert_valid_orcid(bare: str, original: str) -> None:
    """Validate ORCID format and checksum, raising ApiError on failure."""
    if not ORCID_PATTERN.match(bare):
        raise ApiError(
            message=f"Invalid ORCID format: '{original}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    if not _validate_orcid_checksum(bare):
        raise ApiError(
            message=f"Invalid ORCID checksum: '{original}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )


def _assert_valid_ror(bare: str, original: str) -> None:
    """Validate ROR ID format and checksum, raising ApiError on failure."""
    if not ROR_BARE_PATTERN.match(bare):
        raise ApiError(
            message=f"Invalid ROR ID format: '{original}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    if not _validate_ror_checksum(bare):
        raise ApiError(
            message=f"Invalid ROR ID checksum: '{original}'",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )


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


def fetch_orcid_metadata(
    *,
    orcid: str,
    http_client: httpx.Client,
) -> OrcidMetadata:
    """Fetch person metadata from the ORCID Public API.

    Args:
        orcid: validated ORCID identifier (e.g. "0000-0002-1825-0097").
        http_client: shared httpx client instance.

    Returns:
        OrcidMetadata with name information.

    Raises:
        ApiError: if the ORCID cannot be resolved or the response is invalid.
    """
    url = f"{ORCID_API_BASE_URL}/{orcid}/record"

    try:
        response = http_client.request(
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
    except httpx.RequestError as e:
        L.warning("ORCID API request error for %s: %r", orcid, e)
        raise ApiError(
            message="Failed to connect to ORCID API",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        ) from e

    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ApiError(
            message=f"ORCID not found: {orcid}",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    if not response.is_success:
        L.warning("ORCID API error for %s: status %s", orcid, response.status_code)
        raise ApiError(
            message=f"ORCID API returned status {response.status_code}",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        )

    data = response.json()
    person_details = data.get("person", {})
    name_info = person_details.get("name", {}) or {}

    given_name = (name_info.get("given-names") or {}).get("value")
    family_name = (name_info.get("family-name") or {}).get("value")
    credit_name = (name_info.get("credit-name") or {}).get("value")

    pref_label = credit_name or f"{given_name or ''} {family_name or ''}".strip()

    return OrcidMetadata(
        orcid=orcid,
        given_name=given_name,
        family_name=family_name,
        pref_label=pref_label or orcid,
    )


def fetch_ror_metadata(
    *,
    ror_id: str,
    http_client: httpx.Client,
) -> RorMetadata:
    """Fetch organization metadata from the ROR API v2.

    Args:
        ror_id: validated bare ROR identifier (e.g. "03yrm5c26").
        http_client: shared httpx client instance.

    Returns:
        RorMetadata with organization name and type information.

    Raises:
        ApiError: if the ROR ID cannot be resolved or the response is invalid.
    """
    url = f"{ROR_API_BASE_URL}/{ror_id}"

    try:
        response = http_client.request(
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
    except httpx.RequestError as e:
        L.warning("ROR API request error for %s: %r", ror_id, e)
        raise ApiError(
            message="Failed to connect to ROR API",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        ) from e

    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ApiError(
            message=f"ROR ID not found: {ror_id}",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    if not response.is_success:
        L.warning("ROR API error for %s: status %s", ror_id, response.status_code)
        raise ApiError(
            message=f"ROR API returned status {response.status_code}",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        )

    data = response.json()

    # ROR v2 uses "names" array with "types" per name entry
    names = data.get("names", [])
    primary_name = next(
        (n["value"] for n in names if "ror_display" in n.get("types", [])),
        None,
    )
    if not primary_name:
        # Fallback: first name entry, or the raw ID
        primary_name = names[0]["value"] if names else ror_id

    alt_names = [n["value"] for n in names if "ror_display" not in n.get("types", [])]

    org_types = data.get("types", [])

    locations = data.get("locations", [])
    country = (
        locations[0]["geonames_details"]["country_name"]
        if locations and "geonames_details" in locations[0]
        else None
    )

    return RorMetadata(
        ror_id=ror_id,
        name=primary_name,
        alternative_names=alt_names,
        types=org_types,
        country=country,
    )

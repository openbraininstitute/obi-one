"""Service for fetching contributor metadata from ORCID and ROR public APIs.

- ORCID Public API v3.0: https://pub.orcid.org
- ROR API v2: https://api.ror.org

To switch metadata providers, update the implementation in this module without
changing the public interface (fetch_orcid_metadata, fetch_ror_metadata).
"""

import re
from http import HTTPStatus

import httpx

from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.schemas.contributor import OrcidMetadata, RorMetadata
from app.schemas.persistent_identifier import OrcidPersistentIdentifier, RorPersistentIdentifier

ORCID_API_BASE_URL = "https://pub.orcid.org/v3.0"
ROR_API_BASE_URL = "https://api.ror.org/v2/organizations"
ORCID_URL_PREFIX = "https://orcid.org/"
ROR_URL_PREFIX = "https://ror.org/"

ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
ROR_BARE_PATTERN = re.compile(r"^0[a-hj-km-np-tv-z0-9]{6}[0-9]{2}$")


def fetch_orcid_metadata(
    *,
    identifier: OrcidPersistentIdentifier,
    http_client: httpx.Client,
) -> OrcidMetadata:
    """Fetch person metadata from the ORCID Public API.

    Args:
        identifier: ORCID persistent identifier
        http_client: shared httpx client instance.

    Returns:
        OrcidMetadata with name information.

    Raises:
        ApiError: if the ORCID cannot be resolved or the response is invalid.
    """
    bare_orcid = identifier.id
    url = f"{ORCID_API_BASE_URL}/{bare_orcid}/record"

    try:
        response = http_client.request(
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
    except httpx.RequestError as e:
        L.warning("ORCID API request error for %s: %r", bare_orcid, e)
        raise ApiError(
            message="Failed to connect to ORCID API",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        ) from e

    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ApiError(
            message=f"ORCID not found: {bare_orcid}",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    if not response.is_success:
        L.warning("ORCID API error for %s: status %s", bare_orcid, response.status_code)
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
        orcid=bare_orcid,
        given_name=given_name,
        family_name=family_name,
        pref_label=pref_label or bare_orcid,
    )


def fetch_ror_metadata(
    *,
    identifier: RorPersistentIdentifier,
    http_client: httpx.Client,
) -> RorMetadata:
    """Fetch organization metadata from the ROR API v2.

    Args:
        identifier: ROR persistent identifier
        http_client: shared httpx client instance.

    Returns:
        RorMetadata with organization name and type information.

    Raises:
        ApiError: if the ROR ID cannot be resolved or the response is invalid.
    """
    bare_ror = identifier.id
    url = f"{ROR_API_BASE_URL}/{bare_ror}"

    try:
        response = http_client.request(
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
    except httpx.RequestError as e:
        L.warning("ROR API request error for %s: %r", bare_ror, e)
        raise ApiError(
            message="Failed to connect to ROR API",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        ) from e

    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ApiError(
            message=f"ROR ID not found: {bare_ror}",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    if not response.is_success:
        L.warning("ROR API error for %s: status %s", bare_ror, response.status_code)
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
        primary_name = names[0]["value"] if names else bare_ror

    alt_names = [n["value"] for n in names if "ror_display" not in n.get("types", [])]

    org_types = data.get("types", [])

    locations = data.get("locations", [])
    country = (
        locations[0]["geonames_details"]["country_name"]
        if locations and "geonames_details" in locations[0]
        else None
    )

    return RorMetadata(
        ror_id=bare_ror,
        name=primary_name,
        alternative_names=alt_names,
        types=org_types,
        country=country,
    )

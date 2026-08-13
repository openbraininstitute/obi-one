"""Service for fetching publication metadata from a DOI resolver.

Currently uses the Crossref REST API (https://api.crossref.org).
To switch providers, update the implementation in this module without
changing the public interface (fetch_publication_metadata).
"""

from http import HTTPStatus

import httpx

from app.errors import ApiError, ApiErrorCode
from app.logger import L

CROSSREF_API_BASE_URL = "https://api.crossref.org"


def fetch_publication_metadata(
    *,
    doi: str,
    http_client: httpx.Client,
) -> dict:
    """Fetch publication metadata from Crossref for a given DOI.

    Args:
        doi: the DOI identifier (e.g. "10.1038/nature12373").
        http_client: shared httpx client instance.

    Returns:
        A dictionary with keys: DOI, title, authors, publication_year, abstract.

    Raises:
        ApiError: if the DOI cannot be resolved or the response is invalid.
    """
    url = f"{CROSSREF_API_BASE_URL}/works/{doi}"

    try:
        response = http_client.request(
            method="GET",
            url=url,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
    except httpx.RequestError as e:
        L.warning("Crossref API request error for DOI %s: %r", doi, e)
        raise ApiError(
            message="Failed to connect to Crossref API",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        ) from e

    if response.status_code == HTTPStatus.NOT_FOUND:
        raise ApiError(
            message=f"DOI not found in Crossref: {doi}",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    if not response.is_success:
        L.warning("Crossref API error for DOI %s: status %s", doi, response.status_code)
        raise ApiError(
            message=f"Crossref API returned status {response.status_code}",
            error_code=ApiErrorCode.GENERIC_ERROR,
            http_status_code=HTTPStatus.BAD_GATEWAY,
        )

    data = response.json()
    message = data.get("message", {})

    # Extract title (Crossref returns a list of titles)
    titles = message.get("title", [])
    title = titles[0] if titles else None

    # Extract authors
    authors = _extract_authors(message.get("author", []))

    # Extract publication year
    publication_year = _extract_publication_year(message)

    # Extract abstract (may contain HTML/JATS markup — stored as-is)
    abstract = message.get("abstract")

    return {
        "DOI": doi,
        "title": title,
        "authors": authors or None,
        "publication_year": publication_year,
        "abstract": abstract,
    }


def _extract_authors(raw_authors: list[dict]) -> list[dict]:
    """Extract author names from the Crossref response.

    Returns a list of dicts with given_name and family_name keys,
    matching the entitycore Author schema.
    """
    authors: list[dict] = []
    for author in raw_authors:
        given = author.get("given", "")
        family = author.get("family", "")
        if given or family:
            authors.append({"given_name": given, "family_name": family})
    return authors


def _extract_publication_year(message: dict) -> int | None:
    """Extract the publication year from the Crossref metadata.

    Tries published-print, then published-online, then issued.
    """
    for field in ("published-print", "published-online", "issued"):
        date_info = message.get(field, {})
        date_parts = date_info.get("date-parts", [[]])
        if date_parts and date_parts[0] and date_parts[0][0]:
            return int(date_parts[0][0])
    return None

"""Endpoint for user-driven publication registration via DOI lookup."""

import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from starlette.requests import Request

from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.errors import ApiError, ApiErrorCode
from app.services.doi_metadata import fetch_publication_metadata

DOI_REGEX = re.compile(r"^10.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)

router = APIRouter(
    prefix="/declared/publication",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)


class PublicationRegisterRequest(BaseModel):
    """Request body for registering a publication by DOI."""

    DOI: str

    @field_validator("DOI", mode="before")
    @classmethod
    def validate_doi(cls, value: str) -> str:
        """Validate that the provided string is a valid DOI."""
        if not DOI_REGEX.match(value):
            msg = f"Invalid DOI format: {value}"
            raise ValueError(msg)
        return value


@router.post(
    "/register",
    summary="Register a publication by DOI.",
    description=(
        "Registers a new publication in the system by looking up its metadata "
        "(title, authors, year, abstract) from a DOI metadata service. "
        "This avoids manual entry of publication details and reduces data-entry errors."
    ),
    # NOTE: entitycore currently requires admin role to create publications.
    # This endpoint will return 403 for non-admin users.
)
def register_publication(
    json_model: PublicationRegisterRequest,
    db_client: DatabaseClientDep,
    user_context: UserContextDep,  # noqa: ARG001
    request: Request,
) -> dict:
    """Register a publication by fetching metadata from Crossref and creating it in entitycore."""
    from entitysdk import models

    http_client = request.state.http_client
    doi = json_model.DOI

    # Check if publication already exists
    existing = db_client.search_entity(entity_type=models.Publication, query={"DOI": doi}).all()
    if existing:
        raise ApiError(
            message=f"Publication with DOI {doi} is already registered (id={existing[0].id})",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=409,
        )

    # Fetch metadata from Crossref
    metadata = fetch_publication_metadata(doi=doi, http_client=http_client)

    # Register in entitycore via the SDK
    publication = models.Publication(
        DOI=metadata["DOI"],
        title=metadata["title"],
        authors=metadata["authors"],
        publication_year=metadata["publication_year"],
        abstract=metadata["abstract"],
    )
    registered = db_client.register_entity(entity=publication)

    return registered.model_dump(mode="json")

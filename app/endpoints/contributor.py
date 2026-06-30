"""Endpoints for user-driven contributor registration via ORCID/ROR ID lookup."""

from http import HTTPStatus

import httpx
from entitysdk import models
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.requests import Request

from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.errors import ApiError, ApiErrorCode
from app.services.contributor_metadata import (
    IdentifierType,
    OrcidMetadata,
    RorMetadata,
    fetch_orcid_metadata,
    fetch_ror_metadata,
    resolve_identifier,
)

router = APIRouter(
    prefix="/declared/contributor",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)


class ContributorPreview(BaseModel):
    """Preview of a contributor resolved from an identifier."""

    identifier: str
    identifier_type: str
    name: str
    given_name: str | None = None
    family_name: str | None = None
    alternative_name: str | None = None
    agent_type: str  # "person" or "organization"
    already_registered: bool = False
    existing_id: str | None = None


@router.get(
    "",
    summary="Look up a contributor by ORCID or ROR ID.",
    description=(
        "Looks up a contributor by their unique identifier (ORCID for persons, "
        "ROR ID for organizations). Accepts bare identifiers or full URLs "
        "(e.g. https://orcid.org/... or https://ror.org/...). "
        "Returns the existing record if already registered, or a preview of "
        "the metadata resolved from the identifier."
    ),
)
def get_contributor(
    identifier: str,
    db_client: DatabaseClientDep,
    user_context: UserContextDep,  # noqa: ARG001
    request: Request,
) -> ContributorPreview:
    """Look up a contributor by ORCID or ROR ID."""
    http_client = request.state.http_client
    id_type, normalized = resolve_identifier(identifier)
    preview = _build_preview(id_type, normalized, db_client, http_client)
    return preview


@router.post(
    "",
    summary="Register a contributor by ORCID or ROR ID.",
    description=(
        "Registers a new contributor (person or organization) by resolving "
        "metadata from their unique identifier (ORCID or ROR ID). "
        "Accepts bare identifiers or full URLs. "
        "Returns 409 if the contributor is already registered."
    ),
    status_code=HTTPStatus.CREATED,
)
def register_contributor(
    identifier: str,
    db_client: DatabaseClientDep,
    user_context: UserContextDep,  # noqa: ARG001
    request: Request,
) -> dict:
    """Register a contributor by resolving metadata and creating it in entitycore."""
    http_client = request.state.http_client
    id_type, normalized = resolve_identifier(identifier)
    preview = _build_preview(id_type, normalized, db_client, http_client)

    if preview.already_registered:
        raise ApiError(
            message=(
                f"{preview.agent_type.capitalize()} '{preview.name}' is already registered "
                f"(id={preview.existing_id})"
            ),
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
        )

    entity = _create_entity(id_type, preview)
    registered = db_client.register_entity(entity=entity)
    return registered.model_dump(mode="json")


def _build_preview(
    id_type: IdentifierType,
    identifier: str,
    db_client: DatabaseClientDep,
    http_client: httpx.Client,
) -> ContributorPreview:
    """Fetch metadata and check for existing records."""
    # ORCID
    if id_type == IdentifierType.orcid:
        metadata = fetch_orcid_metadata(orcid=identifier, http_client=http_client)
        return _person_preview(identifier, metadata, db_client)

    # ROR ID
    metadata = fetch_ror_metadata(ror_id=identifier, http_client=http_client)
    return _organization_preview(identifier, metadata, db_client)


def _person_preview(
    orcid: str, metadata: OrcidMetadata, db_client: DatabaseClientDep
) -> ContributorPreview:
    """Build a ContributorPreview for a person."""
    existing = db_client.search_entity(entity_type=models.Person, query={"orcid": orcid}).one_or_none()

    return ContributorPreview(
        identifier=orcid,
        identifier_type="orcid",
        name=metadata.pref_label,
        given_name=metadata.given_name,
        family_name=metadata.family_name,
        agent_type="person",
        already_registered=bool(existing),
        existing_id=str(existing[0].id) if existing else None,
    )


def _organization_preview(
    ror_id: str, metadata: RorMetadata, db_client: DatabaseClientDep
) -> ContributorPreview:
    """Build a ContributorPreview for an organization."""
    existing = db_client.search_entity(
        entity_type=models.Organization, query={"ror_id": ror_id}
    ).all()

    return ContributorPreview(
        identifier=ror_id,
        identifier_type="ror",
        name=metadata.name,
        alternative_name=metadata.alternative_names[0] if metadata.alternative_names else None,
        agent_type="organization",
        already_registered=bool(existing),
        existing_id=str(existing[0].id) if existing else None,
    )


def _create_entity(
    id_type: IdentifierType, preview: ContributorPreview
) -> models.Person | models.Organization:
    """Create the entitysdk model from preview data."""
    if id_type == IdentifierType.orcid:
        return models.Person(
            pref_label=preview.name,
            given_name=preview.given_name,
            family_name=preview.family_name,
            orcid=preview.identifier,
        )
    return models.Organization(
        pref_label=preview.name,
        alternative_name=preview.alternative_name,
        ror_id=preview.identifier,
    )

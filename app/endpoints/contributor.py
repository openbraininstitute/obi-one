"""Endpoints for user-driven contributor registration via ORCID/ROR ID lookup."""

from http import HTTPStatus

from entitysdk import models
from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.errors import ApiError, ApiErrorCode
from app.schemas.contributor import OrganizationPreview, PersonPreview
from app.services.contributor_metadata import (
    IdentifierType,
    fetch_orcid_metadata,
    fetch_ror_metadata,
    resolve_identifier,
)

router = APIRouter(
    prefix="/declared/contributor",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)


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
) -> PersonPreview | OrganizationPreview:
    """Look up a contributor by ORCID or ROR ID."""
    id_type, normalized = resolve_identifier(identifier)
    http_client = request.state.http_client

    match id_type:
        case IdentifierType.orcid:
            metadata = fetch_orcid_metadata(orcid=normalized, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Person, query={"orcid": normalized}
            ).one_or_none()
            return PersonPreview(
                identifier=normalized,
                name=metadata.pref_label,
                given_name=metadata.given_name,
                family_name=metadata.family_name,
                orcid=normalized,
                already_registered=existing is not None,
                existing_id=existing.id if existing else None,
            )
        case IdentifierType.ror:
            metadata = fetch_ror_metadata(ror_id=normalized, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Organization, query={"ror_id": normalized}
            ).one_or_none()
            return OrganizationPreview(
                identifier=normalized,
                name=metadata.name,
                alternative_name=(
                    metadata.alternative_names[0] if metadata.alternative_names else None
                ),
                ror_id=normalized,
                already_registered=existing is not None,
                existing_id=existing.id if existing else None,
            )


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
    id_type, normalized = resolve_identifier(identifier)
    http_client = request.state.http_client

    match id_type:
        case IdentifierType.orcid:
            metadata = fetch_orcid_metadata(orcid=normalized, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Person, query={"orcid": normalized}
            ).one_or_none()
            if existing:
                raise ApiError(
                    message=(
                        f"Person '{metadata.pref_label}' is already registered (id={existing.id})"
                    ),
                    error_code=ApiErrorCode.INVALID_REQUEST,
                    http_status_code=HTTPStatus.CONFLICT,
                )
            entity = models.Person(
                pref_label=metadata.pref_label,
                given_name=metadata.given_name,
                family_name=metadata.family_name,
                orcid=f"https://orcid.org/{normalized}",
            )

        case IdentifierType.ror:
            metadata = fetch_ror_metadata(ror_id=normalized, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Organization, query={"ror_id": normalized}
            ).one_or_none()
            if existing:
                raise ApiError(
                    message=(
                        f"Organization '{metadata.name}' is already registered (id={existing.id})"
                    ),
                    error_code=ApiErrorCode.INVALID_REQUEST,
                    http_status_code=HTTPStatus.CONFLICT,
                )
            entity = models.Organization(
                pref_label=metadata.name,
                alternative_name=(
                    metadata.alternative_names[0] if metadata.alternative_names else None
                ),
                ror_id=f"https://ror.org/{normalized}",
            )

    registered = db_client.register_entity(entity=entity)
    return registered.model_dump(mode="json")

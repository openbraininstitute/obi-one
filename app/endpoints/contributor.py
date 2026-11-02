"""Endpoints for user-driven contributor registration via ORCID/ROR ID lookup."""

from http import HTTPStatus

from entitysdk import models
from fastapi import APIRouter, Depends

from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.dependencies.http_client import HttpClientDep
from app.dependencies.persistent_identifier import (
    OrcidPersistentIdentifier,
    PersistentIdentifierDep,
    RorPersistentIdentifier,
)
from app.errors import ApiError, ApiErrorCode
from app.schemas.contributor import OrganizationPreview, PersonPreview
from app.services.contributor import (
    fetch_orcid_metadata,
    fetch_ror_metadata,
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
        "Looks up a contributor by their unique identifier URL "
        "(ORCID for persons, ROR for organizations), e.g. "
        "https://orcid.org/... or https://ror.org/.... "
        "Returns the existing record if already registered, or a preview of "
        "the metadata resolved from the identifier."
    ),
)
def get_contributor(
    db_client: DatabaseClientDep,
    user_context: UserContextDep,  # ruff: ignore[unused-function-argument]
    http_client: HttpClientDep,
    identifier: PersistentIdentifierDep,
) -> PersonPreview | OrganizationPreview:
    """Look up a contributor by ORCID or ROR ID."""
    match identifier:
        case OrcidPersistentIdentifier():
            metadata = fetch_orcid_metadata(identifier=identifier, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Person, query={"orcid": identifier.url}
            ).one_or_none()
            return PersonPreview(
                identifier=identifier.url,
                name=metadata.pref_label,
                given_name=metadata.given_name,
                family_name=metadata.family_name,
                orcid=identifier.url,
                already_registered=existing is not None,
                existing_id=existing.id if existing else None,
            )
        case RorPersistentIdentifier():
            metadata = fetch_ror_metadata(identifier=identifier, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Organization, query={"ror_id": identifier.url}
            ).one_or_none()
            return OrganizationPreview(
                identifier=identifier.url,
                name=metadata.name,
                alternative_name=(
                    metadata.alternative_names[0] if metadata.alternative_names else None
                ),
                ror_id=identifier.url,
                already_registered=existing is not None,
                existing_id=existing.id if existing else None,
            )


@router.post(
    "",
    summary="Register a contributor by ORCID or ROR ID.",
    description=(
        "Registers a new contributor (person or organization) by resolving "
        "metadata from their unique identifier URL (ORCID or ROR). "
        "Returns 409 if the contributor is already registered."
    ),
    status_code=HTTPStatus.CREATED,
)
def register_contributor(
    identifier: PersistentIdentifierDep,
    db_client: DatabaseClientDep,
    user_context: UserContextDep,  # ruff: ignore[unused-function-argument]
    http_client: HttpClientDep,
) -> dict:
    """Register a contributor by resolving metadata and creating it in entitycore."""
    match identifier:
        case OrcidPersistentIdentifier():
            metadata = fetch_orcid_metadata(identifier=identifier, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Person, query={"orcid": identifier.url}
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
                orcid=identifier.url,
            )

        case RorPersistentIdentifier():
            metadata = fetch_ror_metadata(identifier=identifier, http_client=http_client)
            existing = db_client.search_entity(
                entity_type=models.Organization, query={"ror_id": identifier.url}
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
                ror_id=identifier.url,
            )

    registered = db_client.register_entity(entity=entity)
    return registered.model_dump(mode="json")

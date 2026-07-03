"""Endpoints for user-driven subject registration."""

from http import HTTPStatus

from entitysdk import models
from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.errors import ApiError, ApiErrorCode
from app.schemas.subject import SubjectRegisterRequest

router = APIRouter(
    prefix="/declared/subject",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)


@router.get(
    "",
    summary="Search for an existing subject by name.",
    description="Returns the subject if it exists, or 404 if not found.",
)
def get_subject(
    name: str,
    db_client: DatabaseClientDep,
    user_context: UserContextDep,  # noqa: ARG001
) -> dict:
    """Look up a subject by name."""
    existing = db_client.search_entity(
        entity_type=models.Subject, query={"name": name}
    ).one_or_none()

    if not existing:
        raise ApiError(
            message=f"Subject with name '{name}' not found",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    return existing.model_dump(mode="json")


@router.post(
    "",
    summary="Register a new subject.",
    description=(
        "Registers a new subject with the provided metadata. "
        "Returns 409 if a subject with the same name already exists."
    ),
    status_code=HTTPStatus.CREATED,
)
def register_subject(
    json_model: SubjectRegisterRequest,
    db_client: DatabaseClientDep,
    user_context: UserContextDep,  # noqa: ARG001
    request: Request,  # noqa: ARG001
) -> dict:
    """Register a new subject in entitycore."""
    # Check for duplicate name
    existing = db_client.search_entity(
        entity_type=models.Subject, query={"name": json_model.name}
    ).one_or_none()

    if existing:
        raise ApiError(
            message=f"Subject with name '{json_model.name}' already exists (id={existing.id})",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
        )

    # Resolve species (and optionally strain) by ID
    species = db_client.get_entity(entity_type=models.Species, entity_id=json_model.species_id)
    strain = (
        db_client.get_entity(entity_type=models.Strain, entity_id=json_model.strain_id)
        if json_model.strain_id
        else None
    )

    subject = models.Subject(
        name=json_model.name,
        description=json_model.description,
        sex=json_model.sex,
        weight=json_model.weight,
        age_value=json_model.age_value,
        age_min=json_model.age_min,
        age_max=json_model.age_max,
        age_period=json_model.age_period,
        species=species,
        strain=strain,
    )

    registered = db_client.register_entity(entity=subject)
    return registered.model_dump(mode="json")

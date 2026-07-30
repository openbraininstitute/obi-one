"""Endpoints for user-driven subject registration."""

from http import HTTPStatus
from typing import cast

from entitysdk import models
from fastapi import APIRouter, Depends

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.errors import ApiError, ApiErrorCode
from app.schemas.subject import SubjectRegisterRequest, normalize_name, split_name

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


def _find_duplicate_subject_name(db_client: DatabaseClientDep, name: str) -> models.Subject | None:
    """Find a duplicate subject name using normalized comparison.

    Normalizes the input name by lowercasing and stripping all non-alphanumeric
    characters, then searches for candidates via case-insensitive ILIKE and
    compares their normalized forms. This ensures that e.g. "Average Rat",
    "average rat", "AverageRat", "Average-rat", "Average_rat" are all
    considered duplicate names.
    """
    normalized_input = normalize_name(name)
    if not normalized_input:
        return None

    ilike_pattern = "%" + "_".join(split_name(name)) + "%"

    for result in db_client.search_entity(
        entity_type=models.Subject, query={"name__ilike": ilike_pattern}
    ):
        if normalize_name(cast("str", result.name)) == normalized_input:
            return result

    return None


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
) -> dict:
    """Register a new subject in entitycore."""
    existing = _find_duplicate_subject_name(db_client, json_model.name)

    if existing:
        raise ApiError(
            message=f"Subject with name '{json_model.name}' already exists (id={existing.id})",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
        )

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
        age_period=json_model.age_period,
        species=species,
        strain=strain,
    )

    registered = db_client.register_entity(entity=subject)
    return registered.model_dump(mode="json")

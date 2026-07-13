"""Endpoints for user-driven subject registration."""

from http import HTTPStatus

from entitysdk import models
from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.dependencies.auth import UserContextDep, user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.errors import ApiError, ApiErrorCode
from app.schemas.subject import SubjectRegisterRequest, normalize_name_for_comparison

_DUPLICATE_SEARCH_PREFIX_LENGTH = 4

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


def _find_duplicate_subject_name(db_client: DatabaseClientDep, name: str) -> models.Subject | None:
    """Find a duplicate subject name using normalized comparison.

    Normalizes the input name by lowercasing and stripping all non-alphanumeric
    characters, then searches for candidates via case-insensitive ILIKE and
    compares their normalized forms. This ensures that e.g. "Average Rat",
    "average rat", "AverageRat", "Average-rat", "Average_rat" are all
    considered duplicate names.
    """
    normalized_input = normalize_name_for_comparison(name)
    if not normalized_input:
        return None

    # Strategy: build ILIKE patterns that are broad enough to catch all variants.
    # We insert '%' between each alphanumeric character of the normalized name
    # so that "averagerat" becomes "%a%v%e%r%a%g%e%r%a%t%" — this matches any
    # string containing those characters in order regardless of separators.
    # However, this could be too broad for long names and too slow.
    #
    # Practical approach: search using each word of the original name as an ilike
    # fragment with wildcards, PLUS a second search using just the first word.
    # Then compare normalized forms client-side.

    seen_ids: set = set()
    candidates = []

    # Pattern 1: fragments from whitespace-split words
    words = name.lower().split()
    fragments = ["".join(c for c in w if c.isalnum()) for w in words]
    fragments = [f for f in fragments if f]

    if fragments:
        ilike_pattern = "%" + "%".join(fragments) + "%"
        results = db_client.search_entity(
            entity_type=models.Subject, query={"name__ilike": ilike_pattern}
        ).all()
        for r in results:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                candidates.append(r)

    # Pattern 2: if the name has no spaces (e.g. "AverageRat"), also search with
    # a shorter fragment to catch existing entries stored with separators.
    # Use the first few alphanumeric characters as a broad match.
    if len(normalized_input) >= _DUPLICATE_SEARCH_PREFIX_LENGTH:
        short_pattern = f"%{normalized_input[:_DUPLICATE_SEARCH_PREFIX_LENGTH]}%"
        results = db_client.search_entity(
            entity_type=models.Subject, query={"name__ilike": short_pattern}
        ).all()
        for r in results:
            if r.id not in seen_ids:
                seen_ids.add(r.id)
                candidates.append(r)

    for candidate in candidates:
        if normalize_name_for_comparison(candidate.name) == normalized_input:
            return candidate

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
    user_context: UserContextDep,  # noqa: ARG001
    request: Request,  # noqa: ARG001
) -> dict:
    """Register a new subject in entitycore."""
    # Duplicate name detection: normalize by stripping non-alphanumeric chars and lowercasing
    existing = _find_duplicate_subject_name(db_client, json_model.name)

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

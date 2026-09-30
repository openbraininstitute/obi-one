"""Validate a distance-dependent distribution ``function`` string.

The function is a math expression that BluePyEModel evaluates per morphology segment. It is a
security-sensitive input (see ``validate_safe_distance_function``); this endpoint runs the same
safe-AST check and returns the offending character span so the editor can highlight it.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies.auth import user_verified
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
    MAX_DISTANCE_FUNCTION_LENGTH,
    check_distance_function,
)

router = APIRouter(
    prefix="/declared",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)


class DistanceFunctionValidationRequest(BaseModel):
    """Request body for distance-function validation."""

    function: str = Field(max_length=MAX_DISTANCE_FUNCTION_LENGTH)
    # Declared parameter names beyond {value}/{distance} the function may reference.
    parameters: tuple[str, ...] = ()


class DistanceFunctionValidationResponse(BaseModel):
    """Validation result with the error span (character offsets into ``function``)."""

    valid: bool
    error: str | None = None
    from_: int = Field(default=0, alias="from")
    to: int = 0

    model_config = ConfigDict(populate_by_name=True)


@router.post(
    "/distance-function/validate",
    summary="Validate a distance-dependent distribution function",
    description=(
        "Run the safe-AST validation on a distribution function string and return whether it is "
        "valid, plus an error message and the character span of the first problem for editor "
        "highlighting. Stateless; does not evaluate the function."
    ),
)
def validate_distance_function(
    request: DistanceFunctionValidationRequest,
) -> DistanceFunctionValidationResponse:
    """Validate a distance function and return a structured, position-aware result."""
    result = check_distance_function(request.function, request.parameters or None)
    return DistanceFunctionValidationResponse(
        valid=result.valid,
        error=result.error,
        **{"from": result.from_},
        to=result.to,
    )

"""Validate a distance-dependent distribution ``function`` string.

The function is a math expression that BluePyEModel evaluates per morphology segment. It is a
security-sensitive input (see ``validate_safe_distance_function``); this endpoint runs the same
safe-AST check and returns the offending character span so the editor can highlight it. It also
reports which extra placeholders still need a declared parameter, with a fill-in prompt for each,
so the frontend and the AI chat can ask the user for exactly the missing values.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies.auth import user_verified
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import (
    MAX_DISTANCE_FUNCTION_LENGTH,
    DistributionParameterPrompt,
    DistributionParametersCheck,
    check_distance_function,
    check_distribution_parameters,
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
    """Validation result with the error span (character offsets into ``function``).

    ``valid`` is true only when the expression is safe and the declared parameters exactly cover
    its extra placeholders. The ``*_parameters`` lists and ``prompts`` are always filled, so a
    client can prompt for missing names while the user is still typing.
    """

    valid: bool
    error: str | None = None
    from_: int = Field(default=0, alias="from")
    to: int = 0
    required_parameters: tuple[str, ...] = ()
    missing_parameters: tuple[str, ...] = ()
    unknown_parameters: tuple[str, ...] = ()
    duplicate_parameters: tuple[str, ...] = ()
    reserved_parameters: tuple[str, ...] = ()
    prompts: tuple[DistributionParameterPrompt, ...] = ()

    model_config = ConfigDict(populate_by_name=True)


def _parameters_error(check: DistributionParametersCheck) -> str:
    problems = [
        f"{label}: {list(names)}"
        for label, names in (
            ("missing values for placeholders", check.missing_parameters),
            ("declared but unused", check.unknown_parameters),
            ("declared more than once", check.duplicate_parameters),
            ("reserved names", check.reserved_parameters),
        )
        if names
    ]
    return "Distribution parameters do not match the function: " + "; ".join(problems) + "."


@router.post(
    "/distance-function/validate",
    summary="Validate a distance-dependent distribution function",
    description=(
        "Run the safe-AST validation on a distribution function string and return whether it is "
        "valid, plus an error message and the character span of the first problem for editor "
        "highlighting. Also lists the placeholders that need a declared parameter and returns a "
        "fill-in prompt for each missing one. Stateless; does not evaluate the function."
    ),
)
def validate_distance_function(
    request: DistanceFunctionValidationRequest,
) -> DistanceFunctionValidationResponse:
    """Validate a distance function and return a structured, position-aware result."""
    parameters_check = check_distribution_parameters(request.function, request.parameters)
    result = check_distance_function(request.function, request.parameters or None)
    error, start, end = result.error, result.from_, result.to
    if result.valid and not parameters_check.valid:
        error, start, end = _parameters_error(parameters_check), 0, len(request.function)
    return DistanceFunctionValidationResponse(
        valid=result.valid and parameters_check.valid,
        error=error,
        **{"from": start},
        to=end,
        required_parameters=parameters_check.required_parameters,
        missing_parameters=parameters_check.missing_parameters,
        unknown_parameters=parameters_check.unknown_parameters,
        duplicate_parameters=parameters_check.duplicate_parameters,
        reserved_parameters=parameters_check.reserved_parameters,
        prompts=parameters_check.prompts,
    )

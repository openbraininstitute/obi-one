from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from obi_one.core.parametric_multi_values import (
    ParametericMultiValueUnion,
)


def process_value_validation_errors(e: ValidationError) -> None:
    for err in e.errors():
        if err["type"] == "greater_than":
            raise HTTPException(
                status_code=400, detail=f"All values must be > {err['ctx'].get('gt')}"
            ) from e
        if err["type"] == "greater_than_equal":
            raise HTTPException(
                status_code=400, detail=f"All values must be ≥ {err['ctx'].get('ge')}"
            ) from e
        if err["type"] == "less_than":
            raise HTTPException(
                status_code=400, detail=f"All values must be < {err['ctx'].get('lt')}"
            ) from e
        if err["type"] == "less_than_equal":
            raise HTTPException(
                status_code=400, detail=f"All values must be ≤ {err['ctx'].get('le')}"
            ) from e
        if err["type"] == "value_error":
            raise HTTPException(status_code=400, detail=err["msg"]) from e
        if err["type"] == "custom_n_greater_than_max":
            raise HTTPException(status_code=400, detail=err["msg"]) from e


def activate_parameteric_multi_value_endpoint(router: APIRouter) -> None:
    """Fill in later."""
    model_name = "parametric-multi-value"

    # Create endpoint name
    endpoint_name_with_slash = "/" + model_name
    model_description = "Temp description."

    @router.post(endpoint_name_with_slash, summary=model_name, description=model_description)
    def endpoint(
        parameteric_multi_value_type: ParametericMultiValueUnion,
        # Query-level constraints
        ge: Annotated[
            float | int | None, Query(description="Require all values to be ≥ this")
        ] = None,
        gt: Annotated[
            float | int | None, Query(description="Require all values to be > this")
        ] = None,
        le: Annotated[
            float | int | None, Query(description="Require all values to be ≤ this")
        ] = None,
        lt: Annotated[
            float | int | None, Query(description="Require all values to be < this")
        ] = None,
    ) -> list[float] | list[int]:
        try:
            # Create class to allow static annotations with constraints
            class MultiParamHolder(BaseModel):
                multi_value_class: Annotated[
                    ParametericMultiValueUnion, Field(ge=ge, gt=gt, le=le, lt=lt)
                ]

            mvh = MultiParamHolder(
                multi_value_class=parameteric_multi_value_type
            )  # Validate constraints

        except ValidationError as e:
            process_value_validation_errors(e)

        except Exception as e:
            raise HTTPException(status_code=400, detail="Unknown Error") from e

        return list(mvh.multi_value_class)

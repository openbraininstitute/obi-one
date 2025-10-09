import re
import tempfile
from typing import Annotated, get_type_hints

import entitysdk.client
import entitysdk.common
from fastapi import APIRouter, Depends, HTTPException
from fastapi.params import Query
from pydantic import BaseModel, Field, ValidationError

from app.dependencies.entitysdk import get_client
from app.logger import L
from obi_one import run_tasks_for_generated_scan
from obi_one.core.parametric_multi_values import (
    FloatRange,
    IntRange,
    NonNegativeFloatRange,
    NonNegativeIntRange,
    ParametericMultiValue,
    ParametericMultiValueUnion,
    PositiveFloatRange,
    PositiveIntRange,
)
from obi_one.core.scan_config import ScanConfig
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.tasks.contribute import (
    ContributeMorphologyScanConfig,
    ContributeSubjectScanConfig,
)
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsScanConfig,
)
from obi_one.scientific.tasks.simulations import (
    CircuitSimulationScanConfig,
)
from obi_one.scientific.unions.aliases import SimulationsForm


def create_endpoint_for_form(
    model: type[ScanConfig],
    router: APIRouter,
    processing_method: str,
    data_postprocessing_method: str,
) -> None:
    """Create a FastAPI endpoint for generating grid scans based on an OBI ScanConfig model."""
    # model_name: model in lowercase with underscores between words and "Forms" removed (i.e.
    # 'morphology_metrics_example')
    model_base_name = model.__name__.removesuffix("Form")
    model_name = "-".join([word.lower() for word in re.findall(r"[A-Z][^A-Z]*", model_base_name)])

    # Create endpoint name
    endpoint_name_with_slash = "/" + model_name + "-" + processing_method + "-grid"
    if data_postprocessing_method:
        endpoint_name_with_slash = endpoint_name_with_slash + "-" + data_postprocessing_method

    @router.post(endpoint_name_with_slash, summary=model.name, description=model.description)
    def endpoint(
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        form: model,
    ) -> str:
        L.info("generate_grid_scan")
        L.info(db_client)

        campaign = None
        try:
            with tempfile.TemporaryDirectory() as tdir:
                grid_scan = GridScanGenerationTask(
                    form=form,
                    # TODO: output_root=settings.OUTPUT_DIR / "fastapi_test" / model_name
                    #        / "grid_scan", => ERA001 Found commented-out code
                    output_root=tdir,
                    coordinate_directory_option="ZERO_INDEX",
                )
                grid_scan.execute(
                    db_client=db_client,
                )
                campaign = grid_scan.form.campaign
                run_tasks_for_generated_scan(grid_scan, db_client=db_client)

        except Exception as e:
            error_msg = str(e)

            if len(e.args) == 1:
                error_msg = str(e.args[0])
            elif len(e.args) > 1:
                error_msg = str(e.args)

            L.error(error_msg)

            raise HTTPException(status_code=500, detail=error_msg) from e

        else:
            L.info("Grid scan generated successfully")
            if campaign is not None:
                return str(campaign.id)

            L.info("No campaign generated")
            return ""


def create_endpoint_for_parameteric_multi_value_type(
    model: type[ParametericMultiValue], router: APIRouter
) -> None:
    """Fill in later."""

    model_name = "parametric-multi-value"

    # Create endpoint name
    endpoint_name_with_slash = "/" + model_name
    # model.name model.description
    model_name = model.name
    model_description = model.description

    @router.post(endpoint_name_with_slash, summary=model_name, description=model_description)
    def endpoint(
        parameteric_multi_value_type: model,
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
                multi_value_class: Annotated[model, Field(ge=ge, gt=gt, le=le, lt=lt)]

            mvh = MultiParamHolder(
                multi_value_class=parameteric_multi_value_type
            )  # Validate constraints
        except ValidationError as e:
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

        except Exception as e:
            raise HTTPException(status_code=400, detail="Unknown Error") from e

        return list(mvh.multi_value_class)


def activate_generated_endpoints(router: APIRouter) -> APIRouter:
    # Create endpoints for each OBI ScanConfig subclass.
    for form, processing_method, data_postprocessing_method in [
        (CircuitSimulationScanConfig, "generate", ""),
        (SimulationsForm, "generate", "save"),
        (MorphologyMetricsScanConfig, "run", ""),
        (ContributeMorphologyScanConfig, "generate", ""),
        (ContributeSubjectScanConfig, "generate", ""),
    ]:
        create_endpoint_for_form(
            form,
            router,
            processing_method=processing_method,
            data_postprocessing_method=data_postprocessing_method,
        )

    return router


def activate_parameteric_multi_value_endpoints(router: APIRouter) -> APIRouter:
    # Create endpoints for each ParametericMultiValue subclass.

    for parameteric_multi_value_type in [
        ParametericMultiValueUnion,
    ]:
        create_endpoint_for_parameteric_multi_value_type(
            parameteric_multi_value_type,
            router,
        )

    return router

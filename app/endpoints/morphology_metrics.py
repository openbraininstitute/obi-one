from http import HTTPStatus
from typing import Annotated, Literal

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.scientific.library.morphology_metrics import (
    MORPHOLOGY_METRICS,
    MorphologyMetricsOutput,
    get_morphology_metrics,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/neuron-morphology-metrics/{cell_morphology_id}",
    summary="Neuron morphology metrics",
    description=("This calculates neuron morphology metrics for a given cell morphology."),
)
def neuron_morphology_metrics_endpoint(
    cell_morphology_id: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    requested_metrics: Annotated[
        list[Literal[*MORPHOLOGY_METRICS]] | None,  # type: ignore[misc]
        Query(
            description="List of requested metrics",
        ),
    ] = None,
) -> MorphologyMetricsOutput:
    L.info("get_morphology_metrics")
    try:
        metrics = get_morphology_metrics(
            cell_morphology_id=cell_morphology_id,
            db_client=db_client,
            requested_metrics=requested_metrics,
        )
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": (f"Internal error retrieving the cell morphology {cell_morphology_id}."),
            },
        ) from err

    if metrics:
        return metrics
    L.error(f"Cell morphology {cell_morphology_id} metrics computation issue")
    raise ApiError(
        message="Internal error retrieving the asset.",
        error_code=ApiErrorCode.INTERNAL_ERROR,
        http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
    )

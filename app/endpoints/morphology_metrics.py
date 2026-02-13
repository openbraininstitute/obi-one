from http import HTTPStatus
import tempfile
from typing import Annotated, Literal

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.morphology_metrics_calculation import _run_morphology_analysis, register_measurements
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.scientific.library.morphology_metrics import (
    MORPHOLOGY_METRICS,
    MorphologyMetricsOutput,
    get_morphology_metrics,
)
from entitysdk.models.cell_morphology import CellMorphology

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

@router.post(
    "/neuron-morphology-metrics/{cell_morphology_id}/register",
    summary="Compute & register morphology metrics for an existing morphology",
)
def register_morphology_metrics(
    cell_morphology_id: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    # 1) fetch morphology and its SWC asset
    morph = db_client.get_entity(entity_id=cell_morphology_id, entity_type=CellMorphology)
    asset = next((a for a in morph.assets if a.content_type == "application/swc"), None)
    if not asset:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail="No SWC asset on morphology")

    # 2) download to temp file
    with tempfile.NamedTemporaryFile(suffix=".swc") as tmp:
        tmp.write(
            db_client.download_content(
                entity_id=cell_morphology_id, entity_type=CellMorphology, asset_id=asset.id
            )
        )
        tmp.flush()

        # 3) compute measurement_kinds using existing helper
        measurement_kinds = _run_morphology_analysis(tmp.name)

    # 4) register measurement annotation only
    registered = register_measurements(db_client, cell_morphology_id, measurement_kinds)
    return {"measurement_entity_id": str(registered.id), "status": "success"}
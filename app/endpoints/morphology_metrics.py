import tempfile
from enum import StrEnum
from http import HTTPStatus
from typing import Annotated, Any, Literal
from uuid import UUID

import entitysdk.client
import entitysdk.exception
from entitysdk.models.cell_morphology import CellMorphology
from entitysdk.models.measurement_annotation import MeasurementKind
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.endpoints.morphology_metrics_calculation import run_morphology_analysis
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.services.morphology_registration import register_morphometrics
from obi_one.scientific.library.morphology_metrics import (
    MORPHOLOGY_METRICS,
    MorphologyMetricsOutput,
    get_morphology_metrics,
)

MORPHOLOGY_FORMAT_TO_CONTENT_TYPE = {
    "swc": "application/swc",
    "h5": "application/x-hdf5",
    "asc": "application/asc",
}

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

MorphologyMetric = StrEnum("MorphologyMetric", {m: m for m in MORPHOLOGY_METRICS})


@router.get(
    "/neuron-morphology-metrics/{cell_morphology_id}",
    summary="Neuron morphology metrics",
    description=("This calculates neuron morphology metrics for a given cell morphology."),
)
def neuron_morphology_metrics_endpoint(
    cell_morphology_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    requested_metrics: Annotated[
        list[MorphologyMetric] | None,
        Query(
            description="List of requested metrics",
        ),
    ] = None,
) -> MorphologyMetricsOutput:
    L.info("get_morphology_metrics")
    try:
        metrics = get_morphology_metrics(
            cell_morphology_id=str(cell_morphology_id),
            db_client=db_client,
            requested_metrics=list(requested_metrics) if requested_metrics is not None else None,
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


def _run_analysis_with_temp_file(
    content: bytes,
    suffix: Literal[".swc", ".h5", ".asc"],
) -> list[MeasurementKind]:
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(content)
        tmp.flush()
        return run_morphology_analysis(tmp.name)


def compute_measurement_kinds(
    cell_morphology_id: UUID,
    db_client: entitysdk.client.Client,
    morphology_format: str = "h5",
) -> list[MeasurementKind]:
    morphology = db_client.get_entity(
        entity_id=cell_morphology_id,
        entity_type=CellMorphology,
    )

    normalized_format = morphology_format.strip().lower()

    if normalized_format not in MORPHOLOGY_FORMAT_TO_CONTENT_TYPE:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                f"Unsupported morphology format: {normalized_format} "
                f"(expected one of: {', '.join(MORPHOLOGY_FORMAT_TO_CONTENT_TYPE)})"
            ),
        )

    expected_content_type = MORPHOLOGY_FORMAT_TO_CONTENT_TYPE[normalized_format]
    asset = next(
        (a for a in morphology.assets if a.content_type == expected_content_type),
        None,
    )
    if not asset:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(
                f"No {normalized_format.upper()} asset on morphology "
                f"(expected content type: {expected_content_type})"
            ),
        )

    if asset.id is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Morphology asset is missing an id",
        )

    content = db_client.download_content(
        entity_id=cell_morphology_id,
        entity_type=CellMorphology,
        asset_id=asset.id,
    )

    match normalized_format:
        case "swc":
            return _run_analysis_with_temp_file(content, ".swc")
        case "h5":
            return _run_analysis_with_temp_file(content, ".h5")
        case "asc":
            return _run_analysis_with_temp_file(content, ".asc")

    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail=(
            f"Unsupported morphology format: {normalized_format} "
            f"(expected one of: {', '.join(MORPHOLOGY_FORMAT_TO_CONTENT_TYPE)})"
        ),
    )


@router.get(
    "/neuron-morphology-metrics/{cell_morphology_id}/measurement-kinds",
    summary="Preview morphology measurement kinds without registering",
)
def preview_morphology_measurement_kinds(
    cell_morphology_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    morphology_format: Annotated[
        Literal["swc", "h5", "asc"],
        Query(description="Morphology asset format to use for computation"),
    ] = "swc",
) -> dict[str, Any]:
    measurement_kinds = compute_measurement_kinds(
        cell_morphology_id,
        db_client,
        morphology_format=morphology_format,
    )
    return {
        "cell_morphology_id": cell_morphology_id,
        "morphology_format": morphology_format,
        "measurement_kinds": measurement_kinds,
        "status": "success",
    }


@router.post(
    "/neuron-morphology-metrics/{cell_morphology_id}/register",
    summary="Compute & register morphology metrics for an existing morphology",
)
def register_morphology_metrics(
    cell_morphology_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    measurement_kinds = compute_measurement_kinds(
        cell_morphology_id,
        db_client,
        morphology_format="h5",
    )
    try:
        registered = register_morphometrics(db_client, cell_morphology_id, measurement_kinds)
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": (
                    f"Entity measurement registration failed for {cell_morphology_id}: {err}"
                ),
            },
        ) from err

    return {
        "measurement_entity_id": str(registered.id),
        "measurement_kinds": measurement_kinds,
        "status": "success",
    }

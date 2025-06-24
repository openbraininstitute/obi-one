from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.scientific.ephys_extraction.ephys_extraction import (
    ElectrophysiologyMetricsOutput,
    get_electrophysiology_metrics,
)
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MorphologyMetricsOutput,
    get_morphology_metrics,
)


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    @router.get(
        "/neuron-morphology-metrics/{reconstruction_morphology_id}",
        summary="Neuron morphology metrics",
        description="This calculates neuron morphology metrics for a given reconstruction \
                    morphology.",
    )
    def neuron_morphology_metrics_endpoint(
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        reconstruction_morphology_id: str,
    ) -> MorphologyMetricsOutput:
        L.info("get_morphology_metrics")

        try:
            metrics = get_morphology_metrics(
                reconstruction_morphology_id=reconstruction_morphology_id,
                db_client=db_client,
            )
        except entitysdk.exception.EntitySDKError:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": (
                        f"Reconstruction morphology {reconstruction_morphology_id} not found."
                    ),
                },
            )

        if metrics:
            return metrics
        L.error(
            f"Reconstruction morphology {reconstruction_morphology_id} metrics computation issue"
        )
        raise ApiError(
            message="Asset not found",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )

    @router.get(
        "/electrophysiologyrecording-metrics/{trace_id}",
        summary="electrophysiology recording metrics",
        description="This calculates electrophysiology traces metrics for a particular recording",
    )
    def electrophysiologyrecording_metrics_endpoint(
        entity_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        trace_id: str,
    ) -> ElectrophysiologyMetricsOutput:
        L.info("get_electrophysiology_metrics")

        try:
            metrics = get_electrophysiology_metrics(
                trace_id=trace_id,
                entity_client=entity_client,
            )
        except entitysdk.exception.EntitySDKError:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": (f"Electrical cell recording {trace_id} not found."),
                },
            )
        except ValueError:
            raise ApiError(
                message="Asset not found",
                error_code=ApiErrorCode.NOT_FOUND,
                http_status_code=HTTPStatus.NOT_FOUND,
            )
        if metrics:
            return metrics
        L.error(f"electrophysiology recording {trace_id} metrics computation issue")
        raise ApiError(
            message="Asset not found",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        )
    return router

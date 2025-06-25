from http import HTTPStatus
from typing import Annotated, Optional

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.scientific.ephys_extraction.ephys_extraction import (
    ElectrophysiologyMetrics,
    ElectrophysiologyMetricsForm,
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

    @router.post("/electrophysiologyrecording-metrics")
    def electrophysiologyrecording_metrics_endpoint(
        form: ElectrophysiologyMetricsForm,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ) -> ElectrophysiologyMetricsOutput:
        data = form.model_dump()
        data["type"] = "ElectrophysiologyMetrics"
        metrics_model = ElectrophysiologyMetrics.model_validate(data, by_name=True)
        return metrics_model.run(db_client=db_client)

    return router

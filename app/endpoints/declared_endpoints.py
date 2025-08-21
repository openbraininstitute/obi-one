from http import HTTPStatus
from typing import Annotated, Literal

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.core.exception import ProtocolNotFoundError
from obi_one.scientific.ephys_extraction.ephys_extraction import (
    CALCULATED_FEATURES,
    STIMULI_TYPES,
    AmplitudeInput,
    ElectrophysiologyMetricsOutput,
    get_electrophysiology_metrics,
)
from obi_one.scientific.morphology_metrics.morphology_metrics import (
    MORPHOLOGY_METRICS,
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
        reconstruction_morphology_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        requested_metrics: Annotated[
            list[Literal[*MORPHOLOGY_METRICS]] | None,  # type: ignore[misc]
            Query(
                description="List of requested metrics",
            ),
        ] = None,
    ) -> MorphologyMetricsOutput:
        """Calculates neuron morphology metrics for a given reconstruction morphology.

        - **reconstruction_morphology_id**: ID of the reconstruction morphology.
        - **requested_metrics**: List of requested metrics (optional).
        """
        L.info("get_morphology_metrics")

        try:
            metrics = get_morphology_metrics(
                reconstruction_morphology_id=reconstruction_morphology_id,
                db_client=db_client,
                requested_metrics=requested_metrics,
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": (
                        f"Reconstruction morphology {reconstruction_morphology_id} not found."
                    ),
                },
            ) from err

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
        trace_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        requested_metrics: Annotated[CALCULATED_FEATURES | None, Query()] = None,
        amplitude: Annotated[AmplitudeInput, Depends()] = None,
        protocols: Annotated[STIMULI_TYPES | None, Query()] = None,
    ) -> ElectrophysiologyMetricsOutput:
        try:
            ephys_metrics = get_electrophysiology_metrics(
                trace_id=trace_id,
                entity_client=db_client,
                calculated_feature=requested_metrics,
                amplitude=amplitude,
                stimuli_types=protocols,
            )
        except ProtocolNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}") from e
        else:
            return ephys_metrics

    return router

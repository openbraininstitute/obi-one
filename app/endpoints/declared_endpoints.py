from http import HTTPStatus
from typing import Annotated, Literal

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from obi_one.core.exception import ProtocolNotFoundError
from obi_one.scientific.circuit_metrics.circuit_metrics import (
    CircuitMetricsOutput,
    CircuitNodesetsResponse,
    CircuitPopulationsResponse,
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
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


def activate_declared_endpoints(router: APIRouter) -> APIRouter:  # noqa: C901
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

    @router.get(
        "/circuit-metrics/{circuit_id}",
        summary="circuit metrics",
        description="This calculates circuit metrics",
    )
    def circuit_metrics_endpoint(
        circuit_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        level_of_detail_nodes: Annotated[
            CircuitStatsLevelOfDetail,
            Query(
                description="Level of detail for node populations analysis",
            ),
        ] = CircuitStatsLevelOfDetail.none,
        level_of_detail_edges: Annotated[
            CircuitStatsLevelOfDetail,
            Query(
                description="Level of detail for edge populations analysis",
            ),
        ] = CircuitStatsLevelOfDetail.none,
    ) -> CircuitMetricsOutput:
        try:
            # Convert single enum values to dictionaries for ALL_POPULATIONS
            level_of_detail_nodes_dict = {"_ALL_": level_of_detail_nodes}
            level_of_detail_edges_dict = {"_ALL_": level_of_detail_edges}

            circuit_metrics = get_circuit_metrics(
                circuit_id=circuit_id,
                db_client=db_client,
                level_of_detail_nodes=level_of_detail_nodes_dict,
                level_of_detail_edges=level_of_detail_edges_dict,
            )

        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Circuit {circuit_id} not found.",
                },
            ) from err
        return circuit_metrics

    @router.get(
        "/circuit/{circuit_id}/biophysical_populations",
        summary="Circuit populations",
        description="This returns the list of biophysical node populations for a given circuit.",
    )
    def circuit_populations_endpoint(
        circuit_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ) -> CircuitPopulationsResponse:
        """Returns the list of biophysical node populations for a given circuit.

        - **circuit_id**: ID of the circuit.
        """
        try:
            circuit_metrics = get_circuit_metrics(
                circuit_id=circuit_id,
                db_client=db_client,
                level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
                level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Circuit {circuit_id} not found.",
                },
            ) from err

        return CircuitPopulationsResponse(
            populations=circuit_metrics.names_of_biophys_node_populations
        )

    @router.get(
        "/circuit/{circuit_id}/nodesets",
        summary="Circuit nodesets",
        description="This returns the list of nodesets for a given circuit.",
    )
    def circuit_nodesets_endpoint(
        circuit_id: str,
        db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ) -> CircuitNodesetsResponse:
        """Returns the list of nodesets for a given circuit.

        - **circuit_id**: ID of the circuit.
        """
        try:
            circuit_metrics = get_circuit_metrics(
                circuit_id=circuit_id,
                db_client=db_client,
                level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
                level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
            )
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail={
                    "code": ApiErrorCode.NOT_FOUND,
                    "detail": f"Circuit {circuit_id} not found.",
                },
            ) from err

        return CircuitNodesetsResponse(nodesets=circuit_metrics.names_of_nodesets)

    return router

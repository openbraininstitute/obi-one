from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsOutput,
    CircuitNodesetsResponse,
    CircuitPopulationsResponse,
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
from obi_one.scientific.library.entity_property_types import CircuitPropertyType

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.get(
    "/circuit-metrics/{circuit_id}",
    summary="Circuit metrics",
    description="This calculates circuit metrics",
)
def circuit_metrics_endpoint(
    circuit_id: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    level_of_detail_nodes: Annotated[
        CircuitStatsLevelOfDetail,
        Query(description="Level of detail for node populations analysis"),
    ] = CircuitStatsLevelOfDetail.none,
    level_of_detail_edges: Annotated[
        CircuitStatsLevelOfDetail,
        Query(description="Level of detail for edge populations analysis"),
    ] = CircuitStatsLevelOfDetail.none,
) -> CircuitMetricsOutput:
    try:
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
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving the circuit {circuit_id}.",
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
    try:
        circuit_metrics = get_circuit_metrics(
            circuit_id=circuit_id,
            db_client=db_client,
            level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
            level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
        )
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving the circuit {circuit_id}.",
            },
        ) from err
    return CircuitPopulationsResponse(populations=circuit_metrics.names_of_biophys_node_populations)


@router.get(
    "/circuit/{circuit_id}/nodesets",
    summary="Circuit nodesets",
    description="This returns the list of nodesets for a given circuit.",
)
def circuit_nodesets_endpoint(
    circuit_id: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> CircuitNodesetsResponse:
    try:
        circuit_metrics = get_circuit_metrics(
            circuit_id=circuit_id,
            db_client=db_client,
            level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
            level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
        )
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving the circuit {circuit_id}.",
            },
        ) from err
    return CircuitNodesetsResponse(nodesets=circuit_metrics.names_of_nodesets)


@router.get(
    "/mapped-circuit-properties/{circuit_id}",
    summary="Mapped circuit properties",
    description="Returns a dictionary of mapped circuit properties.",
)
def mapped_circuit_properties_endpoint(
    circuit_id: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        circuit_metrics = get_circuit_metrics(
            circuit_id=circuit_id,
            db_client=db_client,
            level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.none},
            level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
        )
        mapped_circuit_properties = {}
        mapped_circuit_properties[CircuitPropertyType.NODE_SET] = circuit_metrics.names_of_nodesets

    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving the circuit {circuit_id}.",
            },
        ) from err
    return mapped_circuit_properties

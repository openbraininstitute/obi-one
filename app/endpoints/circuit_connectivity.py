from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from obi_one.scientific.library.connectivity_metrics import (
    ConnectivityMetricsOutput,
    ConnectivityMetricsRequest,
    get_connectivity_metrics,
)

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


@router.post(
    "/connectivity-metrics/{circuit_id}",
    summary="Connectivity metrics",
    description=(
        "This calculates connectivity metrics, such as connection probabilities and"
        " mean number of synapses per connection between different groups of neurons."
    ),
)
def connectivity_metrics_endpoint(
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    conn_request: ConnectivityMetricsRequest,
) -> ConnectivityMetricsOutput:
    try:
        conn_metrics = get_connectivity_metrics(
            circuit_id=conn_request.circuit_id,
            db_client=db_client,
            edge_population=conn_request.edge_population,
            pre_selection=conn_request.pre_selection,
            pre_node_set=conn_request.pre_node_set,
            post_selection=conn_request.post_selection,
            post_node_set=conn_request.post_node_set,
            group_by=conn_request.group_by,
            max_distance=conn_request.max_distance,
        )
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving the circuit {conn_request.circuit_id}.",
            },
        ) from err
    return conn_metrics

from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from entitysdk.models.circuit import Circuit
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

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
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    CircuitUsability,
)
from obi_one.scientific.library.memodel_circuit import (
    try_get_mechanism_variables,
)
from obi_one.scientific.library.neuronal_manipulation_properties import (
    get_circuit_manipulation_properties,
    get_circuit_node_ids,
)
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetUnion

INPUT_RESISTANCE_DYNAMIC_PARAM = "input_resistance"
router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


# --- Schemas for neuronal manipulation endpoints ---


class NodeIdsRequest(BaseModel):
    """Request body for resolving a neuron set to node IDs."""

    neuron_set: NeuronSetUnion
    population: str | None = None


class NodeIdsResponse(BaseModel):
    """Response for resolved node IDs."""

    population: str
    node_ids: list[int]


class NeuronalManipulationPropertiesRequest(BaseModel):
    """Request body for neuronal manipulation properties."""

    entity_id: str
    neuron_set: NeuronSetUnion | None = None
    node_ids: list[int] | None = None
    population: str | None = None


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
    mapped_circuit_properties: dict = {}

    # Try fetching circuit metrics (nodesets). This succeeds for Circuit entities
    # but fails for MEModel entities which are not stored as Circuit in the DB.
    try:
        circuit_metrics = get_circuit_metrics(
            circuit_id=circuit_id,
            db_client=db_client,
            level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.basic},
            level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
        )
        mapped_circuit_properties[CircuitMappedProperties.NODE_SET] = (
            circuit_metrics.names_of_nodesets
        )
    except (entitysdk.exception.EntitySDKError, ValueError):
        # Expected for MEModel entities or entities without proper circuit configuration
        # Continue to try mechanism variables
        pass

    # Try fetching mechanism variables (succeeds for MEModel entities).
    mechanism_variables_response = try_get_mechanism_variables(
        db_client=db_client,
        entity_id=circuit_id,
    )
    if mechanism_variables_response is not None:
        mapped_circuit_properties[CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL] = (
            mechanism_variables_response
        )

    if not mapped_circuit_properties:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"No properties found for entity {circuit_id}.",
            },
        )

    # Add usability (only for Circuit entities)
    if CircuitMappedProperties.NODE_SET in mapped_circuit_properties:
        try:
            circuit = db_client.get_entity(entity_id=circuit_id, entity_type=Circuit)  # ty:ignore[invalid-argument-type]
            simulation_options_usability = {
                CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI: circuit.scale
                == entitysdk.types.CircuitScale.microcircuit,  # ty:ignore[possibly-missing-submodule]
                CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI: any(
                    INPUT_RESISTANCE_DYNAMIC_PARAM in population.dynamics_param_names  # ty:ignore[unresolved-attribute, unsupported-operator]
                    for population in circuit_metrics.biophysical_node_populations
                ),
            }
            mapped_circuit_properties["usability"] = simulation_options_usability
        except entitysdk.exception.EntitySDKError:
            # If we can't get the circuit entity, set default usability
            mapped_circuit_properties["usability"] = {
                CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI: False,
                CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI: False,
            }
    else:
        # For MEModel entities, set default usability
        mapped_circuit_properties["usability"] = {
            CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI: False,
            CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI: False,
        }

    return mapped_circuit_properties


# --- Neuronal manipulation endpoints ---


@router.post(
    "/circuit/{circuit_id}/node-ids",
    summary="Resolve neuron set to node IDs",
    description="Returns the node IDs for a given neuron set selection in a circuit.",
)
def circuit_node_ids_endpoint(
    circuit_id: str,
    request: NodeIdsRequest,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> NodeIdsResponse:
    try:
        population, node_ids = get_circuit_node_ids(
            db_client=db_client,
            circuit_id=circuit_id,
            neuron_set=request.neuron_set,
            population=request.population,
        )
    except ValueError as err:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(err)) from err
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error resolving node IDs for circuit {circuit_id}.",
            },
        ) from err
    return NodeIdsResponse(population=population, node_ids=node_ids)


@router.post(
    "/neuronal-manipulation-properties",
    summary="Neuronal manipulation properties",
    description="Returns mechanism variables for neuronal manipulation blocks. "
    "Supports both MEModel (single cell) and Circuit (multi-cell) entities.",
)
def neuronal_manipulation_properties_endpoint(
    request: NeuronalManipulationPropertiesRequest,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    # Try MEModel path first
    memodel_result = try_get_mechanism_variables(
        db_client=db_client,
        entity_id=request.entity_id,
    )
    if memodel_result is not None:
        return {
            "entity_type": "memodel",
            "mechanism_variables_by_ion_channel": memodel_result,
        }

    # Circuit path — need either neuron_set or node_ids
    if request.neuron_set is None and request.node_ids is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Either neuron_set or node_ids is required for circuit entities.",
        )

    try:
        result = get_circuit_manipulation_properties(
            db_client=db_client,
            circuit_id=request.entity_id,
            neuron_set=request.neuron_set,
            node_ids=request.node_ids,
            population=request.population,
        )
    except ValueError as err:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(err)) from err
    except entitysdk.exception.EntitySDKError as err:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": (
                    f"Internal error retrieving manipulation properties for {request.entity_id}."
                ),
            },
        ) from err

    return result

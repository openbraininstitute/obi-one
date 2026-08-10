import logging
from http import HTTPStatus
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from entitysdk.models import MEModel
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
    get_memodel_mechanism_variables,
)
from obi_one.scientific.library.neuronal_manipulation_properties import (
    get_circuit_manipulation_properties,
    get_circuit_node_ids,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    NEURONSimulationNeuronSetUnion,
)

L = logging.getLogger(__name__)

INPUT_RESISTANCE_DYNAMIC_PARAM = "input_resistance"
router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


# --- Schemas for neuronal manipulation endpoints ---


class NodeIdsRequest(BaseModel):
    """Request body for resolving a neuron set to node IDs."""

    neuron_set: NEURONSimulationNeuronSetUnion


class NodeIdsResponse(BaseModel):
    """Response for resolved node IDs per population."""

    node_ids_per_population: dict[str, list[int]]


class CircuitNeuronalManipulationPropertiesRequest(BaseModel):
    """Request body for Circuit neuronal manipulation properties."""

    entity_id: str
    neuron_set: NEURONSimulationNeuronSetUnion | None = None


class MemodelNeuronalManipulationPropertiesRequest(BaseModel):
    """Request body for MEModel neuronal manipulation properties."""

    entity_id: str


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
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        circuit_metrics = get_circuit_metrics(
            circuit_id=circuit_id,
            db_client=db_client,
            level_of_detail_nodes={"_ALL_": CircuitStatsLevelOfDetail.basic},
            level_of_detail_edges={"_ALL_": CircuitStatsLevelOfDetail.none},
        )
        mapped_circuit_properties[CircuitMappedProperties.NODE_SET] = (
            circuit_metrics.names_of_nodesets
        )
        mapped_circuit_properties[CircuitMappedProperties.BIOPHYSICAL_NEURONAL_POPULATION] = (
            circuit_metrics.names_of_biophys_node_populations
        )
        mapped_circuit_properties[CircuitMappedProperties.POINT_NEURONAL_POPULATION] = (
            circuit_metrics.names_of_point_node_populations
        )
        mapped_circuit_properties[CircuitMappedProperties.VIRTUAL_NEURONAL_POPULATION] = (
            circuit_metrics.names_of_virtual_node_populations
        )
        mapped_circuit_properties[CircuitMappedProperties.NONVIRTUAL_NEURONAL_POPULATION] = (
            circuit_metrics.names_of_biophys_node_populations
            + circuit_metrics.names_of_point_node_populations
        )
        mapped_circuit_properties[CircuitMappedProperties.NEURONAL_POPULATION] = (
            circuit_metrics.names_of_biophys_node_populations
            + circuit_metrics.names_of_point_node_populations
            + circuit_metrics.names_of_virtual_node_populations
        )
        mapped_circuit_properties[
            CircuitMappedProperties.NODE_PROPERTY_UNIQUE_VALUES_BY_POPULATION
        ] = {
            pop.name: pop.property_unique_values
            for pop in (
                *circuit_metrics.biophysical_node_populations,
                *circuit_metrics.point_node_populations,
                *circuit_metrics.virtual_node_populations,
            )
            if pop is not None
        }
    except (entitysdk.exception.EntitySDKError, ValueError):
        # Expected for MEModel entities or entities without proper circuit configuration.
        # MEModel mechanism variables are served by the dedicated
        # /memodel-neuronal-manipulation-properties endpoint; this endpoint only
        # returns circuit metrics and usability.
        L.info(
            f"Could not retrieve circuit metrics for entity {circuit_id}."
            " This may be expected if the entity is not a Circuit"
            " or is missing circuit configuration.",
        )

    if not mapped_circuit_properties:
        # No circuit metrics were retrieved: validate that the entity exists and is
        # an MEModel so that valid MEModels still receive default usability, while
        # unknown/invalid entities surface as an internal error.
        try:
            db_client.get_entity(entity_id=circuit_id, entity_type=MEModel)  # ty:ignore[invalid-argument-type]
        except entitysdk.exception.EntitySDKError as err:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail={
                    "code": ApiErrorCode.INTERNAL_ERROR,
                    "detail": f"No properties found for entity {circuit_id}.",
                },
            ) from err

    # Add usability (only for Circuit entities)
    if CircuitMappedProperties.NODE_SET in mapped_circuit_properties:
        try:
            circuit = db_client.get_entity(entity_id=circuit_id, entity_type=Circuit)  # ty:ignore[invalid-argument-type]
            simulation_options_usability = {
                CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI: circuit.scale
                == entitysdk.types.CircuitScale.microcircuit,  # ty:ignore[possibly-missing-submodule]
                CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS: circuit.has_morphologies
                and circuit.scale
                in {
                    entitysdk.types.CircuitScale.single,  # ty:ignore[possibly-missing-submodule]
                    entitysdk.types.CircuitScale.pair,  # ty:ignore[possibly-missing-submodule]
                    entitysdk.types.CircuitScale.small,  # ty:ignore[possibly-missing-submodule]
                    entitysdk.types.CircuitScale.microcircuit,  # ty:ignore[possibly-missing-submodule]
                },
                CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI: any(
                    INPUT_RESISTANCE_DYNAMIC_PARAM in population.dynamics_param_names  # ty:ignore[unresolved-attribute, unsupported-operator]
                    for population in circuit_metrics.biophysical_node_populations
                ),
                CircuitUsability.SHOW_BIOPHYSICAL_NEURON_SETS: len(
                    circuit_metrics.names_of_biophys_node_populations
                )
                > 0,
                CircuitUsability.SHOW_POINT_NEURON_SETS: len(
                    circuit_metrics.names_of_point_node_populations
                )
                > 0,
                CircuitUsability.SHOW_VIRTUAL_NEURON_SETS: len(
                    circuit_metrics.names_of_virtual_node_populations
                )
                > 0,
                CircuitUsability.SHOW_NONVIRTUAL_NEURON_SETS: (
                    len(circuit_metrics.names_of_biophys_node_populations)
                    + len(circuit_metrics.names_of_point_node_populations)
                )
                > 0,
                CircuitUsability.SHOW_NEURON_SETS: (
                    len(circuit_metrics.names_of_biophys_node_populations)
                    + len(circuit_metrics.names_of_point_node_populations)
                    + len(circuit_metrics.names_of_virtual_node_populations)
                )
                > 0,
            }
            mapped_circuit_properties["usability"] = simulation_options_usability
        except entitysdk.exception.EntitySDKError:
            # If we can't get the circuit entity, set default usability
            mapped_circuit_properties["usability"] = {
                CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI: False,
                CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS: False,
                CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI: False,
                CircuitUsability.SHOW_BIOPHYSICAL_NEURON_SETS: False,
                CircuitUsability.SHOW_POINT_NEURON_SETS: False,
                CircuitUsability.SHOW_VIRTUAL_NEURON_SETS: False,
                CircuitUsability.SHOW_NONVIRTUAL_NEURON_SETS: False,
                CircuitUsability.SHOW_NEURON_SETS: False,
                CircuitUsability.SHOW_DEPRECATED_BLOCKS: False,
            }
    else:
        # For MEModel entities, set default usability
        mapped_circuit_properties["usability"] = {
            CircuitUsability.SHOW_ELECTRIC_FIELD_STIMULI: False,
            CircuitUsability.SHOW_MORPHOLOGY_LOCATIONS: True,
            CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI: False,
            CircuitUsability.SHOW_BIOPHYSICAL_NEURON_SETS: False,
            CircuitUsability.SHOW_POINT_NEURON_SETS: False,
            CircuitUsability.SHOW_VIRTUAL_NEURON_SETS: False,
            CircuitUsability.SHOW_NONVIRTUAL_NEURON_SETS: False,
            CircuitUsability.SHOW_NEURON_SETS: False,
            CircuitUsability.SHOW_DEPRECATED_BLOCKS: False,
        }

    return mapped_circuit_properties


# --- Neuronal manipulation endpoints ---


@router.post(
    "/circuit/{circuit_id}/neuron-set-node-ids",
    summary="Resolve neuron set to node IDs",
    description="Returns the node IDs for a given neuron set selection in a circuit.",
)
def neuron_set_node_ids(
    circuit_id: str,
    request: NodeIdsRequest,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> NodeIdsResponse:
    try:
        ids_per_population = get_circuit_node_ids(
            db_client=db_client,
            circuit_id=circuit_id,
            neuron_set=request.neuron_set,
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
    return NodeIdsResponse(node_ids_per_population=ids_per_population)


# Circuit-only endpoint.
# MEModel entities get their mechanism variables via the dedicated
# /memodel-neuronal-manipulation-properties endpoint instead.
@router.post(
    "/circuit-neuronal-manipulation-properties-by-neuron-set",
    summary="Circuit neuronal manipulation properties by neuron set",
    description="Returns mechanism variables for neuronal manipulation blocks "
    "for a Circuit entity, resolved by neuron set. "
    "MEModel entities should use /memodel-neuronal-manipulation-properties instead.",
)
def neuronal_manipulation_properties_endpoint_by_neuron_set(
    request: CircuitNeuronalManipulationPropertiesRequest,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        result = get_circuit_manipulation_properties(
            db_client=db_client,
            circuit_id=request.entity_id,
            neuron_set=request.neuron_set,
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


# MEModel-only endpoint.
# Returns mechanism variables for the single emodel backing the MEModel.
# Circuit entities should use
# /circuit-neuronal-manipulation-properties-by-neuron-set instead.
@router.post(
    "/memodel-neuronal-manipulation-properties",
    summary="MEModel neuronal manipulation properties",
    description="Returns mechanism variables for neuronal manipulation blocks "
    "for an MEModel entity. "
    "Circuit entities should use "
    "/circuit-neuronal-manipulation-properties-by-neuron-set instead.",
)
def memodel_neuronal_manipulation_properties_endpoint(
    request: MemodelNeuronalManipulationPropertiesRequest,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> dict:
    try:
        mechanism_variables = get_memodel_mechanism_variables(
            db_client=db_client,
            entity_id=request.entity_id,
        )
    except entitysdk.exception.EntitySDKError as err:
        L.warning("EntitySDK error retrieving MEModel %s", request.entity_id, exc_info=True)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Internal error retrieving MEModel {request.entity_id}: {err}",
            },
        ) from err
    except (ValueError, KeyError, AttributeError) as err:
        # ValueError covers JSONDecodeError and pydantic ValidationError subclasses.
        L.warning(
            "Failed to parse mechanism variables for MEModel %s",
            request.entity_id,
            exc_info=True,
        )
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": (
                    f"Failed to parse mechanism variables for MEModel {request.entity_id}: {err}"
                ),
            },
        ) from err

    return {
        "entity_type": "memodel",
        CircuitMappedProperties.MECHANISM_VARIABLES_BY_ION_CHANNEL: mechanism_variables,
    }

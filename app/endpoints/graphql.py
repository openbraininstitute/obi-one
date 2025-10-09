"""GraphQL endpoints for the obi-one application."""

import json
from enum import Enum
from typing import NewType

import entitysdk.client
import strawberry
from fastapi import Depends
from strawberry.experimental.pydantic import type as pydantic_type
from strawberry.fastapi import GraphQLRouter

from app.dependencies.entitysdk import get_client
from obi_one.scientific.library.circuit_metrics import (
    CircuitMetricsEdgePopulation,
    CircuitMetricsNodePopulation,
    CircuitMetricsOutput,
    CircuitStatsLevelOfDetail,
    get_circuit_metrics,
)
from obi_one.scientific.library.morphology_metrics import (
    MorphologyMetricsOutput,
    get_morphology_metrics,
)

# Create JSON scalar for complex dict fields
JSON = strawberry.scalar(
    NewType("JSON", str),
    serialize=lambda v: json.dumps(v) if v is not None else None,
    parse_value=lambda v: json.loads(v) if v is not None else None,
)


# Create GraphQL enum for morphology metrics
@strawberry.enum
class MorphologyMetric(Enum):
    """Enum for morphology metrics."""

    ASPECT_RATIO = "aspect_ratio"
    CIRCULARITY = "circularity"
    LENGTH_FRACTION_ABOVE_SOMA = "length_fraction_above_soma"
    MAX_RADIAL_DISTANCE = "max_radial_distance"
    NUMBER_OF_NEURITES = "number_of_neurites"
    SOMA_RADIUS = "soma_radius"
    SOMA_SURFACE_AREA = "soma_surface_area"
    TOTAL_LENGTH = "total_length"
    TOTAL_HEIGHT = "total_height"
    TOTAL_WIDTH = "total_width"
    TOTAL_DEPTH = "total_depth"
    TOTAL_AREA = "total_area"
    TOTAL_VOLUME = "total_volume"
    SECTION_LENGTHS = "section_lengths"
    SEGMENT_RADII = "segment_radii"
    NUMBER_OF_SECTIONS = "number_of_sections"
    LOCAL_BIFURCATION_ANGLES = "local_bifurcation_angles"
    REMOTE_BIFURCATION_ANGLES = "remote_bifurcation_angles"
    SECTION_PATH_DISTANCES = "section_path_distances"
    SECTION_RADIAL_DISTANCES = "section_radial_distances"
    SECTION_BRANCH_ORDERS = "section_branch_orders"
    SECTION_STRAHLER_ORDERS = "section_strahler_orders"


@pydantic_type(model=MorphologyMetricsOutput, all_fields=True)
class MorphologyMetricsOutputType:
    """Strawberry type for MorphologyMetricsOutput."""


@pydantic_type(model=CircuitMetricsNodePopulation, all_fields=False)
class CircuitMetricsNodePopulationType:
    """Strawberry type for CircuitMetricsNodePopulation."""
    # Define all fields explicitly, using JSON for dict fields
    number_of_nodes: strawberry.auto
    name: strawberry.auto
    population_type: strawberry.auto
    property_names: strawberry.auto
    property_unique_values: JSON
    property_value_counts: JSON
    node_location_info: JSON | None


@pydantic_type(model=CircuitMetricsEdgePopulation, all_fields=False)
class CircuitMetricsEdgePopulationType:
    """Strawberry type for CircuitMetricsEdgePopulation."""
    # Define all fields explicitly, using JSON for dict fields
    number_of_edges: strawberry.auto
    name: strawberry.auto
    population_type: strawberry.auto
    property_names: strawberry.auto
    property_stats: JSON | None
    degree_stats: JSON | None


@pydantic_type(model=CircuitMetricsOutput, all_fields=True)
class CircuitMetricsOutputType:
    """Strawberry type for CircuitMetricsOutput."""


@strawberry.type
class Query:
    """GraphQL Query root for obi-one API."""

    @strawberry.field
    def hello(self) -> str:
        """Simple test query to verify GraphQL is working."""
        return "Hello from GraphQL!"

    @strawberry.field
    def morphology_metrics(
        self,
        cell_morphology_id: str,
        requested_metrics: list[MorphologyMetric] | None = None,
        info: strawberry.Info = strawberry.UNSET,
    ) -> MorphologyMetricsOutputType:
        """Get morphology metrics for a given cell morphology ID.

        Args:
            cell_morphology_id: The ID of the cell morphology
            requested_metrics: Optional list of specific metrics to calculate (enum values)
            info: Strawberry info object containing request context

        Returns:
            MorphologyMetricsOutputType containing the calculated metrics
        """
        # Get the db_client from the request context
        db_client = info.context.get("db_client")
        if not db_client:
            raise ValueError("Database client not available in context")

        # Convert enum values back to strings for the underlying function
        metrics_strings = None
        if requested_metrics:
            metrics_strings = [metric.value for metric in requested_metrics]

        # Get the Pydantic model instance
        pydantic_result = get_morphology_metrics(
            cell_morphology_id=cell_morphology_id,
            db_client=db_client,
            requested_metrics=metrics_strings,
        )

        # Convert Pydantic instance to Strawberry type
        return MorphologyMetricsOutputType.from_pydantic(pydantic_result)

    @strawberry.field
    def circuit_metrics(
        self,
        circuit_id: str,
        info: strawberry.Info = strawberry.UNSET,
    ) -> CircuitMetricsOutputType:
        """Get circuit metrics for a given circuit ID.

        Args:
            circuit_id: The ID of the circuit
            info: Strawberry info object containing request context

        Returns:
            CircuitMetricsOutputType containing the calculated circuit metrics
        """
        # Get the db_client from the request context
        db_client = info.context.get("db_client")
        if not db_client:
            raise ValueError("Database client not available in context")

        # Auto-detect level of detail from query
        level_of_detail_nodes = _detect_node_level_of_detail(info)
        level_of_detail_edges = _detect_edge_level_of_detail(info)

        # Convert enum values back to CircuitStatsLevelOfDetail
        level_of_detail_nodes_dict = {
            "_ALL_": level_of_detail_nodes
        }
        level_of_detail_edges_dict = {
            "_ALL_": level_of_detail_edges
        }

        # Get the Pydantic model instance
        pydantic_result = get_circuit_metrics(
            circuit_id=circuit_id,
            db_client=db_client,
            level_of_detail_nodes=level_of_detail_nodes_dict,
            level_of_detail_edges=level_of_detail_edges_dict,
        )

        # Convert Pydantic instance to Strawberry type
        return CircuitMetricsOutputType.from_pydantic(pydantic_result)


def _detect_node_level_of_detail(info: strawberry.Info) -> CircuitStatsLevelOfDetail:
    """Detect the required level of detail for node populations based on the query."""
    query_str = str(info.field_nodes)
    
    # Check for advanced fields that require higher levels of detail
    if any(field in query_str for field in [
        "nodeLocationInfo", "propertyUniqueValues", "propertyValueCounts"
    ]):
        return CircuitStatsLevelOfDetail.advanced
    
    # Check for basic fields that require basic level
    if any(field in query_str for field in [
        "biophysicalNodePopulations", "virtualNodePopulations", 
        "propertyNames", "numberOfNodes"
    ]):
        return CircuitStatsLevelOfDetail.basic
    
    # Default to none if only basic counts are requested
    return CircuitStatsLevelOfDetail.none


def _detect_edge_level_of_detail(info: strawberry.Info) -> CircuitStatsLevelOfDetail:
    """Detect the required level of detail for edge populations based on the query."""
    query_str = str(info.field_nodes)
    
    # Check for advanced fields that require higher levels of detail
    if any(field in query_str for field in [
        "propertyStats", "degreeStats"
    ]):
        return CircuitStatsLevelOfDetail.advanced
    
    # Check for basic fields that require basic level
    if any(field in query_str for field in [
        "chemicalEdgePopulations", "electricalEdgePopulations",
        "propertyNames", "numberOfEdges"
    ]):
        return CircuitStatsLevelOfDetail.basic
    
    # Default to none if only basic counts are requested
    return CircuitStatsLevelOfDetail.none


# Create strawberry schema
schema = strawberry.Schema(query=Query)


# Create GraphQL router with context dependency injection
async def get_context(
    db_client: entitysdk.client.Client = Depends(get_client),
):
    """Create GraphQL context with dependencies."""
    return {"db_client": db_client}


graphql_router = GraphQLRouter(
    schema,
    allow_queries_via_get=False,
    context_getter=get_context,
)

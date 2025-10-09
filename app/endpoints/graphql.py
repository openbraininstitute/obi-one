"""GraphQL endpoints for the obi-one application."""

from enum import Enum
from typing import Annotated, Literal

import entitysdk.client
import strawberry
from strawberry.experimental.pydantic import type as pydantic_type
from strawberry.fastapi import GraphQLRouter
from fastapi import Depends

from app.dependencies.entitysdk import get_client
from obi_one.scientific.library.morphology_metrics import (
    MORPHOLOGY_METRICS,
    MorphologyMetricsOutput,
    get_morphology_metrics,
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
    pass


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
        """
        Get morphology metrics for a given cell morphology ID.
        
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

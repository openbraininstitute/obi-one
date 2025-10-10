"""GraphQL endpoints for the obi-one application."""

import io
import json
from enum import Enum
from typing import Annotated, NewType, Dict, Any

import entitysdk.client
import neurom
import strawberry
from entitysdk.models.cell_morphology import CellMorphology
from fastapi import Depends
from neurom import load_morphology
from neurom.core.morphology import Morphology
from strawberry.experimental.pydantic import type as pydantic_type
from strawberry.fastapi import GraphQLRouter
from strawberry.dataloader import DataLoader

from app.dependencies.entitysdk import get_client
from obi_one.scientific.library.morphology_metrics import (
    MorphologyMetricsOutput,
    get_morphology_metrics,
)

# DataLoader for morphology fetching
class MorphologyDataLoader(DataLoader[str, Morphology]):
    def __init__(self, db_client: entitysdk.client.Client):
        super().__init__(load_fn=self._load_morphologies)
        self.db_client = db_client

    async def _load_morphologies(self, cell_morphology_ids: list[str]) -> list[Morphology]:
        """Load multiple morphologies by their IDs."""
        morphologies = []
        for cell_morphology_id in cell_morphology_ids:
            try:
                morphology = self.db_client.get_entity(entity_id=cell_morphology_id, entity_type=CellMorphology)

                for asset in morphology.assets:
                    if asset.content_type == "application/swc":
                        content = self.db_client.download_content(
                            entity_id=morphology.id,
                            entity_type=CellMorphology,
                            asset_id=asset.id,
                        ).decode(encoding="utf-8")

                        neurom_morphology = load_morphology(io.StringIO(content), reader="swc")
                        morphologies.append(neurom_morphology)
                        break
                else:
                    raise ValueError(f"No SWC asset found for CellMorphology with ID {cell_morphology_id}")
            except Exception as e:
                # Handle individual failures gracefully
                morphologies.append(None)
        return morphologies


# Context getter for GraphQL
async def get_context(db_client: entitysdk.client.Client = Depends(get_client)) -> Dict[str, Any]:
    """Create GraphQL context with dependencies."""
    return {
        "db_client": db_client,
        "morphology_loader": MorphologyDataLoader(db_client)
    }


# Types
@strawberry.type
class MultipleValuesContainer:
    values: list[float]
    length: int
    mean: float
    std: float



@strawberry.type
class MorphologyMetrics:
    """Morphology metrics container."""
    
    def __init__(self, morphology: Morphology):
        self.morphology = morphology
    
    @strawberry.field(description="Aspect ratio of the morphology.")
    def aspect_ratio(self) -> float:
        return neurom.get("aspect_ratio", self.morphology)
    
    @strawberry.field(description="Total length of the morphology in micrometers.")
    def total_length(self) -> float:
        return neurom.get("total_length", self.morphology)
    
    @strawberry.field(description="Number of sections in the morphology.")
    def number_of_sections(self) -> int:
        return neurom.get("number_of_sections", self.morphology)


@strawberry.type
class Query:
    """GraphQL Query root for obi-one API."""

    @strawberry.field(description="Get morphology metrics for a specific cell morphology ID.")
    async def morphology_metrics(self, info: strawberry.Info, cell_morphology_id: str) -> MorphologyMetrics:
        """Get morphology metrics for a specific cell morphology ID."""
        morphology_loader = info.context["morphology_loader"]
        # The DataLoader will handle caching and batching
        morphology = await morphology_loader.load(cell_morphology_id)
        return MorphologyMetrics(morphology)

    @strawberry.field
    async def hello(self) -> str:
        """Simple test query to verify GraphQL is working."""
        return "Hello from GraphQL!"


# Create strawberry schema
schema = strawberry.Schema(query=Query)


graphql_router = GraphQLRouter(
    schema,
    context_getter=get_context,
    allow_queries_via_get=False,
)

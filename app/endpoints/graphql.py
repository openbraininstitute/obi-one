"""GraphQL endpoints for the obi-one application."""

import io
import json
from enum import Enum
from typing import Annotated, NewType, Dict, Any
import numpy as np

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
    
    def _get_list_metric(self, metric_name: str) -> MultipleValuesContainer:
        """Helper method to get list metrics and convert to MultipleValuesContainer."""
        values = neurom.get(metric_name, self.morphology)
        if values is None:
            return MultipleValuesContainer(values=[], length=0, mean=0.0, std=0.0)
        
        # Convert numpy array to list of floats
        values_list = values.tolist() if hasattr(values, 'tolist') else list(values)
        values_array = np.array(values_list)
        
        return MultipleValuesContainer(
            values=values_list,
            length=len(values_list),
            mean=float(np.mean(values_array)) if len(values_array) > 0 else 0.0,
            std=float(np.std(values_array)) if len(values_array) > 0 else 0.0
        )
    
    @strawberry.field(description="Aspect ratio of the morphology.")
    def aspect_ratio(self) -> float:
        return neurom.get("aspect_ratio", self.morphology)
    
    @strawberry.field(description="Circularity of the morphology points along the plane.")
    def circularity(self) -> float:
        return neurom.get("circularity", self.morphology)
    
    @strawberry.field(description="Length fraction of segments with midpoints higher than soma.")
    def length_fraction_above_soma(self) -> float:
        return neurom.get("length_fraction_above_soma", self.morphology)
    
    @strawberry.field(description="Maximum radial distance from the soma in micrometers.")
    def max_radial_distance(self) -> float:
        return neurom.get("max_radial_distance", self.morphology)
    
    @strawberry.field(description="Number of neurites in the morphology.")
    def number_of_neurites(self) -> int:
        return neurom.get("number_of_neurites", self.morphology)
    
    @strawberry.field(description="Radius of the soma in micrometers.")
    def soma_radius(self) -> float:
        return neurom.get("soma_radius", self.morphology)
    
    @strawberry.field(description="Surface area of the soma in square micrometers.")
    def soma_surface_area(self) -> float:
        return neurom.get("soma_surface_area", self.morphology)
    
    @strawberry.field(description="Total length of the morphology neurites in micrometers.")
    def total_length(self) -> float:
        return neurom.get("total_length", self.morphology)
    
    @strawberry.field(description="Total height (Y-range) of the morphology in micrometers.")
    def total_height(self) -> float:
        return neurom.get("total_height", self.morphology)
    
    @strawberry.field(description="Total width (X-range) of the morphology in micrometers.")
    def total_width(self) -> float:
        return neurom.get("total_width", self.morphology)
    
    @strawberry.field(description="Total depth (Z-range) of the morphology in micrometers.")
    def total_depth(self) -> float:
        return neurom.get("total_depth", self.morphology)
    
    @strawberry.field(description="Total surface area of all sections in square micrometers.")
    def total_area(self) -> float:
        return neurom.get("total_area", self.morphology)
    
    @strawberry.field(description="Total volume of all sections in cubic micrometers.")
    def total_volume(self) -> float:
        return neurom.get("total_volume", self.morphology)
    
    @strawberry.field(description="Distribution of lengths per section in micrometers.")
    def section_lengths(self) -> MultipleValuesContainer:
        return self._get_list_metric("section_lengths")
    
    @strawberry.field(description="Distribution of radii of the morphology in micrometers.")
    def segment_radii(self) -> MultipleValuesContainer:
        return self._get_list_metric("segment_radii")
    
    @strawberry.field(description="Number of sections in the morphology.")
    def number_of_sections(self) -> int:
        return neurom.get("number_of_sections", self.morphology)
    
    @strawberry.field(description="Angles between sections computed at bifurcation (local) in radians.")
    def local_bifurcation_angles(self) -> MultipleValuesContainer:
        return self._get_list_metric("local_bifurcation_angles")
    
    @strawberry.field(description="Angles between sections computed at section ends (remote) in radians.")
    def remote_bifurcation_angles(self) -> MultipleValuesContainer:
        return self._get_list_metric("remote_bifurcation_angles")
    
    @strawberry.field(description="Path distances from soma to section endpoints in micrometers.")
    def section_path_distances(self) -> MultipleValuesContainer:
        return self._get_list_metric("section_path_distances")
    
    @strawberry.field(description="Radial distance from soma to section endpoints in micrometers.")
    def section_radial_distances(self) -> MultipleValuesContainer:
        return self._get_list_metric("section_radial_distances")
    
    @strawberry.field(description="Distribution of branch orders of sections, computed from soma.")
    def section_branch_orders(self) -> MultipleValuesContainer:
        return self._get_list_metric("section_branch_orders")
    
    @strawberry.field(description="Distribution of strahler branch orders of sections, computed from terminals.")
    def section_strahler_orders(self) -> MultipleValuesContainer:
        return self._get_list_metric("section_strahler_orders")


@strawberry.type
class Query:
    """GraphQL Query root for obi-one API."""

    @strawberry.field(description="Get morphology metrics for a specific cell morphology ID.")
    async def morphology_metrics(self, info: strawberry.Info, cell_morphology_id: str) -> MorphologyMetrics:
        """Get morphology metrics for a specific cell morphology ID."""
        morphology_loader = info.context["morphology_loader"]
        # The DataLoader will handle caching and batching
        morphology = await morphology_loader.load(cell_morphology_id)
        
        if morphology is None:
            raise ValueError(f"Morphology with ID '{cell_morphology_id}' not found or could not be loaded")
        
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

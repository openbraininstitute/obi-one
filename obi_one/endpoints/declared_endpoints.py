from app.config import settings
from app.dependencies.auth import UserContextDep
from app.dependencies.entitysdk import get_client
from app.logger import L

from pydantic import BaseModel, Field
from typing import Annotated
from fastapi import Depends

from pathlib import Path
import io
import tempfile

import entitysdk.client
import entitysdk.common

from fastapi import APIRouter

from entitysdk.models.morphology import ReconstructionMorphology
from neurom import load_morphology
import neurom

def activate_declared_router(router: APIRouter) -> APIRouter:

    class ReconstructionMorphologyMetricsOutput(BaseModel):

        aspect_ratio: Annotated[float, Field(title="aspect_ratio", description="Calculates the min/max ratio of the principal direction extents along the plane.")]
        circularity: Annotated[float, Field(title="circularity", description="Calculates the circularity of the morphology points along the plane.")]
        length_fraction_above_soma: Annotated[float, Field(title="length_fraction_above_soma", description="Returns the length fraction of the segments that have their midpoints higher than the soma.")]
        max_radial_distance: Annotated[float, Field(title="max_radial_distance", description="Get the maximum radial distances of the termination sections.")]
        number_of_neurites: Annotated[int, Field(title="number_of_neurites", description="Number of neurites in a morph.")]

        soma_radius: Annotated[float, Field(title="soma_radius [µm]", description="The radius of the soma in micrometers.")]
        soma_surface_area: Annotated[float, Field(title="soma_surface_area [µm^2]", description="The surface area of the soma in square micrometers.")]
        
    
    @router.get("/neuron_morphology_metrics/{reconstruction_morphology_id}", summary="Neuron morphology metrics", description="This calculates neuron morphology metrics for a given reconstruciton morphology.")
    async def neuron_morphology_metrics_endpoint(entity_client: Annotated[entitysdk.client.Client, Depends(get_client)], 
                        reconstruction_morphology_id: str) -> ReconstructionMorphologyMetricsOutput:

        L.info("neurom_metrics")

        try:

            # Get the reconstruction morphology from entity core
            morphology = entity_client.get_entity(
                            entity_id=reconstruction_morphology_id, entity_type=ReconstructionMorphology
                        )
            
            # Iterate through the assets of the morphology to find the one with content type "application/asc"
            for asset in morphology.assets:
                if asset.content_type == "application/asc":

                    # Download the content into memory
                    content = entity_client.download_content(
                                entity_id=morphology.id, entity_type=ReconstructionMorphology, asset_id=asset.id
                            ).decode(encoding="utf-8")

                    # Use StringIO to create a file-like object in memory from the string content
                    neurom_morphology = load_morphology(io.StringIO(content), reader="asc")
                    

                    # Calculate the soma radius and surface area and return the ReconstructionMorphologyMetricsOutput object
                    output = ReconstructionMorphologyMetricsOutput(
                        aspect_ratio=neurom.get("aspect_ratio", neurom_morphology),
                        circularity=neurom.get("circularity", neurom_morphology),
                        length_fraction_above_soma=neurom.get("length_fraction_above_soma", neurom_morphology),
                        max_radial_distance=neurom.get("max_radial_distance", neurom_morphology),
                        # neurite_volume_density=neurom.get("neurite_volume_density", neurom_morphology),
                        number_of_neurites=neurom.get("number_of_neurites", neurom_morphology),
                        # list_of_number_of_sections_per_neurite=neurom.get("list_of_number_of_sections_per_neurite", neurom_morphology),
                        # section_bif_radial_distances=neurom.get("section_bif_radial_distances", neurom_morphology),

                        soma_radius=neurom.get("soma_radius", neurom_morphology),
                        soma_surface_area=neurom.get("soma_surface_area", neurom_morphology),
                    )
                    return output

        except Exception:  # noqa: BLE001
            L.exception("Generic exception")


    return router






# """Useful for loading into file"""

# morphology_path = Path(settings.OUTPUT_DIR / "obi-entity-file-store" / asset.full_path)
# L.info(f"morphology_path: {morphology_path}")
# morphology_path.parent.mkdir(parents=True, exist_ok=True)

# entity_client.download_file(
#     entity_id=morphology.id,
#     entity_type=ReconstructionMorphology,
#     asset_id=asset.id,
#     output_path=morphology_path,
# )

# neurom_morphology = load_morphology(morphology_path)
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
        soma_radius: Annotated[float, Field(title="soma_radius [µm]", description="The radius of the soma in micrometers.")]
        soma_surface_area: Annotated[float, Field(title="soma_surface_area [µm^2]", description="The surface area of the soma in square micrometers.")]
        
    
    @router.get("/neurom_metrics/{reconstruction_morphology_id}", summary="NeuroM Metrics", description="Takes a single NeuroM morphology and returns the soma radius and surface area.")
    async def endpoint(entity_client: Annotated[entitysdk.client.Client, Depends(get_client)], 
                        reconstruction_morphology_id: str) -> ReconstructionMorphologyMetricsOutput:

        L.info("neurom_metrics")

        try:

            # Get the reconstruction morphology from entity core
            morphology = entity_client.get_entity(
                            entity_id=reconstruction_morphology_id, entity_type=ReconstructionMorphology
                        )
            
            # Iterate through the assets of the morphology to find the one with content type "application/h5"
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
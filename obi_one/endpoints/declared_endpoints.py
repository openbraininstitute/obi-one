from app.config import settings
from app.dependencies.auth import UserContextDep
from app.dependencies.entitysdk import get_client
from app.logger import L

from pydantic import BaseModel, Field
from typing import Annotated
from fastapi import Depends

import entitysdk.client
import entitysdk.common

from fastapi import APIRouter

from entitysdk.models.morphology import ReconstructionMorphology
from neurom import load_morphology

def activate_declared_router(router: APIRouter) -> APIRouter:

    class ReconstructionMorphologyMetricsOutput(BaseModel):
        soma_radius: Annotated[float, Field(title="soma_radius [µm]", description="The radius of the soma in micrometers.")]
        soma_surface_area: Annotated[float, Field(title="soma_surface_area [µm^2]", description="The surface area of the soma in square micrometers.")]
        
    
    @router.get("/neurom_metrics/{reconstruction_morphology_id}", summary="NeuroM Metrics", description="Takes a single NeuroM morphology and returns the soma radius and surface area.")
    async def endpoint(entity_client: Annotated[entitysdk.client.Client, Depends(get_client)], 
                        reconstruction_morphology_id: str) -> ReconstructionMorphologyMetricsOutput:

        L.info("neurom_metrics")

        try:

            morphology = entity_client.get_entity(
                            entity_id=reconstruction_morphology_id, entity_type=ReconstructionMorphology, token=client.token
                        )
            L.info(f"morphology: {morphology}")

            morphology_path = ""
            for asset in morphology.assets:
                if asset['content_type'] == "application/asc":

                    morphology_path = Path(settings.OUTPUT_DIR / "obi-entity-file-store" / asset['full_path'])
                    print(file_output_path)
                    morphology_path.parent.mkdir(parents=True, exist_ok=True)

                    client.download_file(
                        entity_id=morphology.id,
                        entity_type=entity_type,
                        asset_id=asset['id'],
                        output_path=morphology_path,
                        token=db.token,
                    )

            if morphology_path == "":
                L.exception("Generic exception")
            else:
                neurom_morphology = load_morphology(morphology_path)

                output = ReconstructionMorphologyMetricsOutput(
                    soma_radius=neurom.get("soma_radius", neurom_morphology),
                    soma_surface_area=neurom.get("soma_surface_area", neurom_morphology),
                )

                return output

        except Exception:  # noqa: BLE001
            L.exception("Generic exception")


    return router


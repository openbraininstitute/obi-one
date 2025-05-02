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

def activate_declared_router(router: APIRouter) -> APIRouter:

    class ReconstructionMorphologyMetricsOutput(BaseModel):
        soma_radius: Annotated[float, Field(title="soma_radius [µm]", description="The radius of the soma in micrometers.")]
        soma_surface_area: Annotated[float, Field(title="soma_surface_area [µm^2]", description="The surface area of the soma in square micrometers.")]
        
    
    @router.get("/neurom_metrics/{reconstruction_morphology_id}", summary="NeuroM Metrics", description="Takes a single NeuroM morphology and returns the soma radius and surface area.")
    async def endpoint(entity_client: Annotated[entitysdk.client.Client, Depends(get_client)], 
                        reconstruction_morphology_id: str) -> ReconstructionMorphologyMetricsOutput:

        L.info("neurom_metrics")

        try:
            output = ReconstructionMorphologyMetricsOutput(
                soma_radius=self.initialize.morphology.neurom_morphology,
                soma_surface_area=self.initialize.morphology.neurom_morphology,
            )

            return output

        except Exception:  # noqa: BLE001
            L.exception("Generic exception")


    return router


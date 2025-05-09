import io
from typing import Annotated

import entitysdk.client
import entitysdk.common
from entitysdk.models.morphology import ReconstructionMorphology
from fastapi import APIRouter, Depends, HTTPException
from neurom import load_morphology

from app.dependencies.entitysdk import get_client
from app.logger import L
from obi_one.scientific.morphology_metrics.morphology_metrics import MorphologyMetricsOutput


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    @router.get(
        "/neuron-morphology-metrics/{reconstruction_morphology_id}",
        summary="Neuron morphology metrics",
        description="This calculates neuron morphology metrics for a given reconstruction morphology.",
    )
    async def neuron_morphology_metrics_endpoint(
        entity_client: Annotated[entitysdk.client.Client, Depends(get_client)],
        reconstruction_morphology_id: str,
    ) -> MorphologyMetricsOutput:
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
                        entity_id=morphology.id,
                        entity_type=ReconstructionMorphology,
                        asset_id=asset.id,
                    ).decode(encoding="utf-8")

                    # Use StringIO to create a file-like object in memory from the string content
                    neurom_morphology = load_morphology(io.StringIO(content), reader="asc")

                    # Calculate the metrics using neurom
                    morphology_metrics = MorphologyMetricsOutput.from_morphology(neurom_morphology)

                    return morphology_metrics

        except Exception as e:  # noqa: BLE001
            L.exception(f"An error occurred: {e}")
            raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")

    return router


# from pathlib import Path
# from app.config import settings

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

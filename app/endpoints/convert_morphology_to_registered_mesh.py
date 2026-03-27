import io
import tempfile
from http import HTTPStatus
from pathlib import Path
from typing import Annotated

import entitysdk.client
import entitysdk.exception
from entitysdk.common import ProjectContext
from entitysdk.models.cell_morphology import CellMorphology
from fastapi import APIRouter, Depends, HTTPException, Query
from nmm.common import NEURON_COLORS
from nmm.morphology import NeuronMorphology

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiError, ApiErrorCode
from app.logger import L

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


def _mesh_swc(swc_path: str, output_directory: str) -> str:
    """Convert a SWC file to an annotated GLB mesh and return the output file path."""
    morphology = NeuronMorphology(
        swc_path,
        smooth_sections=True,
        soma_color=NEURON_COLORS.SOMA,
        axon_color=NEURON_COLORS.AXON,
        basal_dendrite_color=NEURON_COLORS.BASAL_DENDRITE,
        apical_dendrite_color=NEURON_COLORS.APICAL_DENDRITE,
    )
    return morphology.export_annotated_glb_mesh(output_directory=output_directory, show_stats=False)


@router.post(
    "/convert-morphology-to-registered-mesh/{cell_morphology_id}",
    summary="Compute & register a GLB surface mesh for an existing morphology",
    description=(
        "Downloads the SWC asset for the given cell morphology, converts it to an annotated "
        "GLB mesh using neuromorphomesh, uploads the result as a new asset on the same entity, "
        "and returns the new asset id."
    ),
)
def register_morphology_mesh(
    cell_morphology_id: str,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
    virtual_lab_id: Annotated[str, Query(description="Virtual lab ID")],
    project_id: Annotated[str, Query(description="Project ID")],
) -> dict:
    db_client.project_context = ProjectContext(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
    )
    # ------------------------------------------------------------------
    # 1. Fetch the CellMorphology entity
    # ------------------------------------------------------------------
    print(f"db_client config: url={db_client.api_url}, project={db_client.project_context}")

    L.info(f"db_client config: url={db_client.api_url}, project={db_client.project_context}")
    L.info(f"register_morphology_mesh: fetching entity {cell_morphology_id}")
    try:
        morph = db_client.get_entity(entity_id=cell_morphology_id, entity_type=CellMorphology)
    except entitysdk.exception.EntitySDKError as err:
        L.error(f"Failed to fetch entity {cell_morphology_id}: {err}")
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail={
                "code": ApiErrorCode.NOT_FOUND,
                "detail": f"Cell morphology {cell_morphology_id} not found.",
            },
        ) from err

    # ------------------------------------------------------------------
    # 2. Locate the SWC asset
    # ------------------------------------------------------------------
    swc_asset = next((a for a in morph.assets if a.content_type == "application/swc"), None)
    if swc_asset is None:
        L.error(f"No SWC asset found on morphology {cell_morphology_id}")
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Cell morphology {cell_morphology_id} has no SWC asset.",
            },
        )

    # ------------------------------------------------------------------
    # 3. Download SWC content into memory
    # ------------------------------------------------------------------
    L.info(f"register_morphology_mesh: downloading SWC asset {swc_asset.id}")
    try:
        swc_bytes: bytes = db_client.download_content(
            entity_id=cell_morphology_id,
            entity_type=CellMorphology,
            asset_id=swc_asset.id,
        )
    except entitysdk.exception.EntitySDKError as err:
        L.error(f"Failed to download SWC asset {swc_asset.id}: {err}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": "Failed to download the SWC asset.",
            },
        ) from err

    if not swc_bytes:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "code": ApiErrorCode.VALIDATION_ERROR,
                "detail": "Downloaded SWC asset is empty.",
            },
        )

    # ------------------------------------------------------------------
    # 4. Mesh the SWC file; both the SWC input and GLB output are kept
    #    in a single temporary directory that is cleaned up automatically.
    # ------------------------------------------------------------------
    L.info(f"register_morphology_mesh: meshing {cell_morphology_id}")
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            safe_id = Path(cell_morphology_id).name
            swc_path = Path(tmp_dir) / f"{safe_id}.swc"
            swc_path.write_bytes(swc_bytes)

            glb_path_str = _mesh_swc(str(swc_path), output_directory=tmp_dir)
            glb_path = Path(glb_path_str)

            if not glb_path.exists() or glb_path.stat().st_size == 0:
                raise RuntimeError(f"Meshing produced no output at {glb_path_str}")

            # ----------------------------------------------------------------
            # 5. Upload the GLB as a new asset on the same entity
            # ----------------------------------------------------------------
            L.info(
                f"register_morphology_mesh: uploading GLB asset for {cell_morphology_id} "
                f"({glb_path.stat().st_size} bytes)"
            )
            try:
                asset = db_client.upload_file(
                    entity_id=cell_morphology_id,
                    entity_type=CellMorphology,
                    file_path=glb_path,
                    file_content_type="model/gltf-binary",
                    asset_label="cell_surface_mesh",
                )
            except entitysdk.exception.EntitySDKError as err:
                L.error(f"Failed to upload GLB asset for {cell_morphology_id}: {err}")
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail={
                        "code": ApiErrorCode.INTERNAL_ERROR,
                        "detail": "Failed to upload the GLB mesh asset.",
                    },
                ) from err

    except HTTPException:
        raise
    except Exception as err:
        L.error(f"Meshing failed for {cell_morphology_id}: {err}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"Meshing failed: {err}",
            },
        ) from err

    L.info(f"register_morphology_mesh: done, asset id={asset.id}")
    return {"asset_id": str(asset.id), "status": "success"}

import tempfile
import uuid
from http import HTTPStatus
from pathlib import Path

import entitysdk.client
import entitysdk.exception
from entitysdk.models.asset import Asset
from entitysdk.models.cell_morphology import CellMorphology
from entitysdk.types import AssetLabel, ContentType
from fastapi import APIRouter, Depends

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import DatabaseClientDep
from app.errors import ApiError, ApiErrorCode
from app.logger import L

try:
    from nmm.common import NEURON_COLORS
    from nmm.morphology import NeuronMorphology

    HAS_MESHING = True
except ImportError:
    HAS_MESHING = False

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


def _mesh_swc(swc_path: str, output_directory: str) -> str:
    morphology = NeuronMorphology(
        swc_path,
        smooth_sections=True,
        soma_color=NEURON_COLORS.SOMA,
        axon_color=NEURON_COLORS.AXON,
        basal_dendrite_color=NEURON_COLORS.BASAL_DENDRITE,
        apical_dendrite_color=NEURON_COLORS.APICAL_DENDRITE,
    )
    return morphology.export_annotated_glb_mesh(output_directory=output_directory, show_stats=False)


def _check_no_existing_glb_assets(
    db_client: entitysdk.client.Client,
    cell_morphology_id: uuid.UUID,
    morph: CellMorphology,
) -> None:
    existing_glb_asset = db_client.select_assets(
        entity=morph,
        selection={
            "content_type": ContentType.model_gltf_binary,
            "label": AssetLabel.cell_surface_mesh,
        },
    ).first()
    if existing_glb_asset is not None:
        L.error(
            f"register_morphology_mesh: GLB asset already exists for {cell_morphology_id}: "
            f"{existing_glb_asset.id}"
        )
        raise ApiError(
            message=f"Cell morphology {cell_morphology_id} already has a GLB asset.",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.CONFLICT,
            details={"asset_id": existing_glb_asset.id},
        )


def _upload_glb_asset(
    db_client: entitysdk.client.Client,
    cell_morphology_id: uuid.UUID,
    glb_path: Path,
) -> Asset:
    L.info(
        f"register_morphology_mesh: uploading GLB asset for {cell_morphology_id} "
        f"({glb_path.stat().st_size} bytes)"
    )
    try:
        return db_client.upload_file(
            entity_id=cell_morphology_id,
            entity_type=CellMorphology,
            file_path=glb_path,
            file_content_type=ContentType.model_gltf_binary,
            asset_label=AssetLabel.cell_surface_mesh,
        )
    except entitysdk.exception.EntitySDKError as err:
        L.error(f"Failed to upload GLB asset for {cell_morphology_id}: {err}")
        raise ApiError(
            message="Failed to upload the GLB mesh asset.",
            error_code=ApiErrorCode.DATABASE_CLIENT_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(err),
        ) from err


def _validate_mesh_output(glb_path: Path, glb_path_str: str) -> None:
    if not glb_path.exists():
        msg = f"Meshing produced no output at {glb_path_str}"
        raise RuntimeError(msg)

    if glb_path.stat().st_size == 0:
        msg = f"Meshing produced blank output at {glb_path_str}"
        raise RuntimeError(msg)


def mesh_and_register(
    db_client: entitysdk.client.Client,
    cell_morphology_id: uuid.UUID,
    swc_bytes: bytes,
) -> Asset:
    """Convert SWC bytes to a GLB mesh and upload it as an asset on the given morphology."""
    L.info(f"register_morphology_mesh: meshing {cell_morphology_id}")
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            swc_path = Path(tmp_dir) / f"{uuid.uuid4()}.swc"
            swc_path.write_bytes(swc_bytes)

            glb_path_str = _mesh_swc(str(swc_path), output_directory=tmp_dir)
            glb_path = Path(glb_path_str)

            _validate_mesh_output(glb_path, glb_path_str)

            return _upload_glb_asset(db_client, cell_morphology_id, glb_path)

    except ApiError:
        raise
    except Exception as err:
        L.error(f"Meshing failed for {cell_morphology_id}: {err}")
        raise ApiError(
            message=f"Meshing failed for morphology {cell_morphology_id}.",
            error_code=ApiErrorCode.INTERNAL_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(err),
        ) from err


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
    cell_morphology_id: uuid.UUID,
    db_client: DatabaseClientDep,
) -> dict:
    if not HAS_MESHING:
        raise ApiError(
            message="Meshing dependencies are not installed on this instance.",
            error_code=ApiErrorCode.INTERNAL_ERROR,
            http_status_code=HTTPStatus.NOT_IMPLEMENTED,
        )
    try:
        morph = db_client.get_entity(entity_id=cell_morphology_id, entity_type=CellMorphology)
    except entitysdk.exception.EntitySDKError as err:
        L.error(f"Failed to fetch entity {cell_morphology_id}: {err}")
        raise ApiError(
            message=f"Cell morphology {cell_morphology_id} not found.",
            error_code=ApiErrorCode.NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
        ) from err

    L.info(f"register_morphology_mesh: checking for existing GLB assets on {cell_morphology_id}")
    _check_no_existing_glb_assets(db_client, cell_morphology_id, morph)

    try:
        swc_asset = db_client.select_assets(
            entity=morph,
            selection={"content_type": ContentType.application_swc, "label": AssetLabel.morphology},
        ).one()
    except entitysdk.exception.IteratorResultError as err:
        L.error(f"No SWC asset found on morphology {cell_morphology_id}: {err}")
        raise ApiError(
            message=f"Cell morphology {cell_morphology_id} has no SWC asset.",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from err

    L.info(f"register_morphology_mesh: downloading SWC asset {swc_asset.id}")
    try:
        swc_bytes: bytes = db_client.download_content(
            entity_id=cell_morphology_id,
            entity_type=CellMorphology,
            asset_id=swc_asset.id,
        )
    except entitysdk.exception.EntitySDKError as err:
        L.error(f"Failed to download SWC asset {swc_asset.id}: {err}")
        raise ApiError(
            message="Failed to download the SWC asset.",
            error_code=ApiErrorCode.DATABASE_CLIENT_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            details=str(err),
        ) from err

    if not swc_bytes:
        raise ApiError(
            message="Downloaded SWC asset is empty.",
            error_code=ApiErrorCode.INVALID_REQUEST,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    asset = mesh_and_register(db_client, cell_morphology_id, swc_bytes)

    L.info(f"register_morphology_mesh: done, asset id={asset.id}")
    return {"asset_id": str(asset.id), "status": "success"}

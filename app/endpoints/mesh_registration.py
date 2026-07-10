import pathlib
from typing import Annotated
from uuid import UUID

import entitysdk.client
import pylmesh
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel, ContentType
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.dependencies.entitysdk import get_client
from app.endpoints.mesh_validation import _save_upload_to_tempfile
from app.logger import L
from obi_one.scientific.library.mesh_lod_generation import try_generate_and_upload_lods

router = APIRouter(prefix="/declared", tags=["mesh-registration"])

SUPPORTED_SUFFIXES = {".obj", ".glb"}


class MeshRegistrationResponse(BaseModel):
    entity_id: str
    glb_asset_id: str
    lod_generation_status: str
    status: str


def _convert_obj_to_glb(obj_path: pathlib.Path, glb_path: pathlib.Path) -> pathlib.Path:
    """Convert a Wavefront .obj mesh to binary glTF (.glb) using pylmesh.

    Raises:
        RuntimeError: if the OBJ has no geometry or the conversion fails.
    """
    mesh = pylmesh.load_mesh(str(obj_path))
    if mesh.is_empty():
        msg = f"OBJ file '{obj_path}' contains no geometry"
        raise RuntimeError(msg)

    glb_path.parent.mkdir(parents=True, exist_ok=True)
    pylmesh.save_mesh(str(glb_path), mesh)
    return glb_path


def _replace_existing_asset_if_present(
    client: entitysdk.client.Client,
    entity_id: UUID,
    file_name: str,
) -> None:
    """Delete any existing asset on this entity with the same file name, if one exists."""
    entity = client.get_entity(entity_id=entity_id, entity_type=EMCellMesh)
    existing = next((a for a in entity.assets if a.path.endswith(file_name)), None)
    if existing is not None and existing.id is not None:
        L.info(f"Replacing existing asset '{file_name}' on entity {entity_id}")
        client.delete_asset(entity_id=entity_id, entity_type=EMCellMesh, asset_id=existing.id)


async def _generate_lods_background_task(
    client: entitysdk.client.Client,
    entity_id: UUID,
    lod_source_path: pathlib.Path,
    lod_mesh_format: str,
) -> None:
    """Runs after the HTTP response has already been sent. Owns cleanup of lod_source_path."""
    try:
        result = await try_generate_and_upload_lods(
            client, entity_id, lod_source_path, lod_mesh_format
        )
        L.info(
            f"[register-mesh] background LOD generation finished for entity {entity_id}, "
            f"result={result}",
        )
    finally:
        await run_in_threadpool(lod_source_path.unlink, missing_ok=True)


@router.post("/{entity_id}/register-mesh")
async def register_mesh(
    entity_id: UUID,
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
) -> MeshRegistrationResponse:

    original_name = pathlib.Path(file.filename or "mesh")
    original_suffix = original_name.suffix.lower()
    if original_suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported mesh file extension '{original_suffix}'. Expected .obj or .glb.",
        )

    temp_mesh_path = pathlib.Path(_save_upload_to_tempfile(file, suffix=original_suffix))
    glb_path = temp_mesh_path
    lod_source_path = temp_mesh_path
    lod_mesh_format = original_suffix.lstrip(".")
    glb_file_name = original_name.with_suffix(".glb").name

    try:
        if original_suffix == ".obj":
            glb_path = temp_mesh_path.with_name(f"{temp_mesh_path.stem}_converted.glb")
            await run_in_threadpool(_convert_obj_to_glb, temp_mesh_path, glb_path)
            lod_source_path = temp_mesh_path
            lod_mesh_format = "obj"

        await run_in_threadpool(
            _replace_existing_asset_if_present, client, entity_id, glb_file_name
        )

        glb_asset = await run_in_threadpool(
            client.upload_file,
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_path=glb_path,
            file_name=glb_file_name,
            file_content_type=ContentType.model_gltf_binary,
            asset_label=AssetLabel("cell_surface_mesh"),
        )

        if glb_path != temp_mesh_path:
            await run_in_threadpool(glb_path.unlink, missing_ok=True)

        background_tasks.add_task(
            _generate_lods_background_task,
            client,
            entity_id,
            lod_source_path,
            lod_mesh_format,
        )

        return MeshRegistrationResponse(
            entity_id=str(entity_id),
            glb_asset_id=str(glb_asset.id),
            lod_generation_status="started",
            status="success",
        )

    except HTTPException:
        await run_in_threadpool(temp_mesh_path.unlink, missing_ok=True)
        if glb_path != temp_mesh_path:
            await run_in_threadpool(glb_path.unlink, missing_ok=True)
        raise
    except Exception as exc:
        await run_in_threadpool(temp_mesh_path.unlink, missing_ok=True)
        if glb_path != temp_mesh_path:
            await run_in_threadpool(glb_path.unlink, missing_ok=True)
        L.error(f"Registration failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

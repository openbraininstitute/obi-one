import pathlib
from typing import Annotated
from uuid import UUID, uuid4

import entitysdk.client
import httpx
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel, ContentType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.config import settings
from app.dependencies.compute_cell import ComputeCellDep
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.mesh_validation import _save_upload_to_tempfile
from app.logger import L

router = APIRouter(prefix="/declared", tags=["mesh-registration"])


class MeshRegistrationResponse(BaseModel):
    entity_id: str
    glb_asset_id: str
    task_job_id: str
    status: str


class LodGenerationResponse(BaseModel):
    entity_id: str
    source_asset_id: str
    source_mesh_format: str
    task_job_id: str
    status: str


def _ensure_project_context(client: entitysdk.client.Client) -> None:
    """Helper to validate project context existence, satisfying TRY301."""
    if client.project_context is None:
        raise HTTPException(status_code=500, detail="Project context missing")


def _delete_existing_assets(
    client: entitysdk.client.Client,
    entity_id: UUID,
    label: AssetLabel,
) -> None:
    """Delete any existing assets with the given label so the new upload replaces them."""
    entity = client.get_entity(entity_id=entity_id, entity_type=EMCellMesh)
    for asset in client.select_assets(entity=entity, selection={"label": label}):
        L.info(f"Deleting existing asset {asset.id} (label={label}) on entity {entity_id}")
        client.delete_asset(entity_id=entity_id, entity_type=EMCellMesh, asset_id=asset.id)


def _resolve_source_mesh_asset(
    client: entitysdk.client.Client,
    entity_id: UUID,
) -> tuple[UUID, str]:
    """Pick the source mesh asset to generate LODs from.

    Prefers an existing obj asset; falls back to glb if no obj is present.
    """
    entity = client.get_entity(entity_id=entity_id, entity_type=EMCellMesh)
    mesh_assets = list(
        client.select_assets(entity=entity, selection={"label": AssetLabel("cell_surface_mesh")})
    )

    obj_asset = next(
        (a for a in mesh_assets if a.content_type == ContentType.application_obj), None
    )
    if obj_asset is not None:
        return obj_asset.id, "obj"

    glb_asset = next(
        (a for a in mesh_assets if a.content_type == ContentType.model_gltf_binary), None
    )
    if glb_asset is not None:
        return glb_asset.id, "glb"

    msg = f"Entity {entity_id} has no obj or glb cell_surface_mesh asset"
    raise HTTPException(status_code=404, detail=msg)


def _trigger_mesh_lod_generation_task(
    *,
    ls_client: httpx.Client,
    entity_id: UUID,
    mesh_asset_id: UUID,
    mesh_format: str,
    project_id: UUID,
    virtual_lab_id: UUID,
    compute_cell: str,
) -> UUID:
    """Submit a mesh LOD generation job directly to the launch-system."""
    launch_path = "launch_scripts/launch_mesh_lod_generation"
    job_data = {
        "code": {
            "type": "python_repository",
            "location": settings.OBI_ONE_REPO,
            "ref": f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}",
            "path": f"{launch_path}/main.py",
            "dependencies": (
                "launch_scripts/launch_mesh_lod_generation/dependencies/mesh_lod_generation.txt"
            ),
            "capabilities": {"private_packages": True},
        },
        "resources": {
            "type": "machine",
            "cores": 4,
            "memory": 8,
            "timelimit": "01:00",
            "compute_cell": compute_cell,
        },
        "inputs": [
            f"--entity_id {entity_id}",
            f"--mesh_asset_id {mesh_asset_id}",
            f"--mesh_format {mesh_format}",
            f"--virtual_lab_id {virtual_lab_id}",
            f"--project_id {project_id}",
        ],
        "project_id": str(project_id),
        "callbacks": [],
    }

    response = ls_client.post(url="/job", json=job_data)
    if not response.is_success:
        msg = f"Failed to submit mesh LOD generation job: {response.text}"
        raise HTTPException(status_code=500, detail=msg)

    return UUID(response.json()["id"])


@router.post("/{entity_id}/register-mesh")
async def register_mesh(
    entity_id: UUID,
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ls_client: LaunchSystemClientDep,
    compute_cell: ComputeCellDep,
    file: Annotated[UploadFile, File()],
    lod_mesh_format: Annotated[str, Form()] = "obj",
) -> MeshRegistrationResponse:
    temp_mesh_path = pathlib.Path(_save_upload_to_tempfile(file, suffix=".glb"))
    unique_filename = f"{entity_id}_{uuid4().hex[:8]}.glb"

    _ensure_project_context(client)
    project_context = client.project_context
    if project_context is None:
        raise HTTPException(status_code=500, detail="Project context missing")

    try:
        await run_in_threadpool(
            _delete_existing_assets, client, entity_id, AssetLabel("cell_surface_mesh")
        )

        glb_asset = await run_in_threadpool(
            client.upload_file,
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_path=temp_mesh_path,
            file_name=unique_filename,
            file_content_type=ContentType.model_gltf_binary,
            asset_label=AssetLabel("cell_surface_mesh"),
        )

        job_id = await run_in_threadpool(
            _trigger_mesh_lod_generation_task,
            ls_client=ls_client,
            entity_id=entity_id,
            mesh_asset_id=glb_asset.id,
            mesh_format=lod_mesh_format,
            project_id=project_context.project_id,
            virtual_lab_id=project_context.virtual_lab_id,  # ty:ignore[invalid-argument-type]
            compute_cell=compute_cell,
        )

        return MeshRegistrationResponse(
            entity_id=str(entity_id),
            glb_asset_id=str(glb_asset.id),
            task_job_id=str(job_id),
            status="pending",
        )

    except Exception as exc:
        L.error(f"Registration failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{entity_id}/generate-lod")
async def generate_lod_from_entity(
    entity_id: UUID,
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ls_client: LaunchSystemClientDep,
    compute_cell: ComputeCellDep,
) -> LodGenerationResponse:
    """Generate and register the LOD mesh directory for already-registered EMCellMesh.

    Prefers the entity's obj asset if one exists; falls back to its glb asset otherwise.
    """
    _ensure_project_context(client)
    project_context = client.project_context
    if project_context is None:
        raise HTTPException(status_code=500, detail="Project context missing")

    try:
        mesh_asset_id, mesh_format = await run_in_threadpool(
            _resolve_source_mesh_asset, client, entity_id
        )

        job_id = await run_in_threadpool(
            _trigger_mesh_lod_generation_task,
            ls_client=ls_client,
            entity_id=entity_id,
            mesh_asset_id=mesh_asset_id,
            mesh_format=mesh_format,
            project_id=project_context.project_id,
            virtual_lab_id=project_context.virtual_lab_id,  # ty:ignore[invalid-argument-type]
            compute_cell=compute_cell,
        )

        return LodGenerationResponse(
            entity_id=str(entity_id),
            source_asset_id=str(mesh_asset_id),
            source_mesh_format=mesh_format,
            task_job_id=str(job_id),
            status="pending",
        )

    except HTTPException:
        raise
    except Exception as exc:
        L.error(f"LOD generation from entity failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

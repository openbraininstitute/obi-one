import pathlib
from typing import Annotated, cast
from uuid import UUID, uuid4

import entitysdk.client
import httpx
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel, ContentType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.config import settings
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


def _ensure_project_context(client: entitysdk.client.Client) -> None:
    """Helper to validate project context existence, satisfying TRY301."""
    if client.project_context is None:
        raise HTTPException(status_code=500, detail="Project context missing")


def _trigger_mesh_lod_generation_task(
    *,
    ls_client: httpx.Client,
    entity_id: UUID,
    mesh_asset_id: UUID,
    mesh_format: str,
    project_id: UUID,
    virtual_lab_id: UUID,
) -> UUID:
    """Submit a mesh LOD generation job directly to the launch-system."""
    launch_path = "launch_scripts/launch_mesh_lod_generation"
    job_data = {
        "code": {
            "type": "python_repository",
            "location": settings.OBI_ONE_REPO,
            "ref": f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}",
            "path": f"{launch_path}/main.py",
            "dependencies": f"{launch_path}/dependencies/mesh_lod_generation.txt",
            "capabilities": {"private_packages": True},
        },
        "resources": {
            "type": "machine",
            "cores": 4,
            "memory": 8,
            "timelimit": "01:00",
            "compute_cell": "local",
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
            mesh_asset_id=cast("UUID", glb_asset.id),
            mesh_format=lod_mesh_format,
            project_id=project_context.project_id,  # ty:ignore[invalid-argument-type]
            virtual_lab_id=project_context.virtual_lab_id,  # ty:ignore[invalid-argument-type]
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

import json
import pathlib
import tempfile
from typing import Annotated
from uuid import UUID, uuid4

import entitysdk.client
from entitysdk.models import EMCellMesh, TaskConfig
from entitysdk.types import ContentType
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.dependencies.callback import CallBackUrlDep
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.mesh_validation import _save_upload_to_tempfile
from app.logger import L
from app.mappings import TASK_DEFINITIONS
from app.services import task as task_service
from app.types import TaskType
from obi_one.scientific.tasks.mesh_lod_generation.config import MeshLodGenerationSingleConfig

router = APIRouter(prefix="/declared", tags=["mesh-registration"])


class MeshRegistrationResponse(BaseModel):
    entity_id: str
    glb_asset_id: str
    task_job_id: str
    activity_id: str | None = None
    status: str


def _register_task_config(
    client: entitysdk.client.Client, entity_id: UUID, mesh_asset_id: UUID, mesh_format: str
) -> UUID:
    lod_config = MeshLodGenerationSingleConfig(
        entity_id=str(entity_id),
        mesh_asset_id=str(mesh_asset_id),
        mesh_format=mesh_format,
    )

    config_payload = lod_config.model_dump(mode="json")
    config_payload.update(
        {
            "idx": -1,
            "scan_output_root": ".",
            "coordinate_output_root": ".",
            "type": "MeshLodGenerationSingleConfig",
        }
    )

    config_entity = client.register_entity(
        TaskConfig(
            name=f"LOD Generation for {entity_id}",
            description="Auto-generated LOD configuration",
            task_config_type="mesh_lod_generation__config",
            meta={"scan_parameters": config_payload},
            inputs=[],
        )
    )

    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".json", encoding="utf-8", delete=False
    ) as tmp:
        json.dump(config_payload, tmp)
        tmp_path = tmp.name

    try:
        client.upload_file(
            entity_id=config_entity.id,
            entity_type=TaskConfig,
            file_path=tmp_path,
            file_name="task_config.json",
            file_content_type="application/json",
            asset_label="task_config",
        )
    finally:
        pathlib.Path(tmp_path).unlink()

    return config_entity.id


@router.post("/{entity_id}/register-mesh")
async def register_mesh(
    entity_id: UUID,
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ls_client: LaunchSystemClientDep,
    callback_url: CallBackUrlDep,
    file: Annotated[UploadFile, File()],
    lod_mesh_format: Annotated[str, Form()] = "obj",
) -> MeshRegistrationResponse:

    temp_mesh_path = pathlib.Path(_save_upload_to_tempfile(file, suffix=".glb"))

    unique_filename = f"{entity_id}_{uuid4().hex[:8]}.glb"

    try:
        glb_asset = await run_in_threadpool(
            client.upload_file,
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_path=temp_mesh_path,
            file_name=unique_filename,
            file_content_type=ContentType.model_gltf_binary.value,
            asset_label="cell_surface_mesh",
        )

        config_id = await run_in_threadpool(
            _register_task_config, client, entity_id, glb_asset.id, lod_mesh_format
        )

        L.info(f"Submitting with Project Context: {client.project_context.project_id}")

        task_info = await run_in_threadpool(
            task_service.submit_task_job,
            db_client=client,
            ls_client=ls_client,
            callback_url=callback_url,
            config_id=config_id,
            project_context=client.project_context,
            task_definition=TASK_DEFINITIONS[TaskType.mesh_lod_generation],
            callbacks=[],
        )

        activity_id = None
        if isinstance(task_info, dict):
            activity_id = task_info.get("activity_id")
        else:
            activity_id = getattr(task_info, "activity_id", None)

        return MeshRegistrationResponse(
            entity_id=str(entity_id),
            glb_asset_id=str(glb_asset.id),
            task_job_id=str(getattr(task_info, "job_id", "unknown")),
            activity_id=str(activity_id) if activity_id else None,
            status="pending",
        )

    except Exception as exc:
        L.error(f"Registration failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

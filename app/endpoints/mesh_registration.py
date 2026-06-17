import json
import pathlib
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk.client
from entitysdk.common import ProjectContext
from entitysdk.exception import EntitySDKError
from entitysdk.models import EMCellMesh, Entity, TaskConfig
from entitysdk.types import AssetLabel, ContentType, TaskConfigType
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.dependencies.callback import CallBackUrlDep
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.mesh_validation import (
    _cleanup_temp_file,
    _save_upload_to_tempfile,
    validate_mesh_reader,
)
from app.errors import ApiErrorCode
from app.logger import L
from app.mappings import TASK_DEFINITIONS
from app.services import task as task_service
from app.types import TaskType

router = APIRouter(
    prefix="/declared",
    tags=["mesh-registration"],
)


class MeshRegistrationResponse(BaseModel):
    entity_id: str
    obj_asset_id: str
    task_job_id: str
    status: str


def _require_uuid(value: UUID | None, msg: str) -> UUID:
    if value is None:
        raise ValueError(msg)
    return value


def _register_obj_asset(
    client: entitysdk.client.Client,
    entity_id: UUID,
    obj_path: pathlib.Path,
) -> UUID:
    L.info(f"Uploading OBJ asset for entity {entity_id} …")

    try:
        with obj_path.open("rb") as f:
            file_content = f.read()

        asset = client.upload_content(
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_content=file_content,
            file_name=obj_path.name,
            file_content_type=ContentType.application_obj,
            asset_label=AssetLabel.cell_surface_mesh,
        )

        asset_id = _require_uuid(
            asset.id,
            "Uploaded asset has no valid ID.",
        )

        L.info(f"OBJ asset uploaded successfully: {asset_id}")

    except (EntitySDKError, ValueError) as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"Failed to upload OBJ asset to entitysdk: {exc}",
            },
        ) from exc

    return asset_id


def _create_lod_task_config(
    client: entitysdk.client.Client,
    entity_id: UUID,
    obj_asset_id: UUID,
) -> UUID:
    L.info(f"Creating LOD generation TaskConfig for entity {entity_id} …")

    config_payload = json.dumps(
        {
            "type": "MeshLodGenerationSingleConfig",
            "entity_id": str(entity_id),
            "obj_asset_id": str(obj_asset_id),
        }
    ).encode()

    try:
        task_config_instance = TaskConfig(
            task_config_type=TaskConfigType.mesh_lod_generation__config,
            name=f"Mesh LOD generation config for {entity_id}",
            description="Auto-generated config for mesh LOD generation task.",
            inputs=[Entity(id=entity_id)],
            meta={},
        )

        config_entity = client.register_entity(task_config_instance)

        config_entity_id = _require_uuid(
            config_entity.id,
            "Registered TaskConfig entity has no valid ID.",
        )

        client.upload_content(
            entity_id=config_entity_id,
            entity_type=TaskConfig,
            file_content=config_payload,
            file_name="config.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.task_config,
        )

    except (EntitySDKError, ValueError) as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"LOD TaskConfig creation failed: {exc}",
            },
        ) from exc

    L.info(f"LOD TaskConfig created: {config_entity_id}")
    return config_entity_id


def _ensure_project_context(client: entitysdk.client.Client) -> ProjectContext:
    if client.project_context is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Client project context is missing.",
        )
    return client.project_context


@router.post(
    "/{entity_id}/register-mesh",
    status_code=HTTPStatus.ACCEPTED,
)
async def register_mesh_and_generate_lods(
    entity_id: str,
    file: Annotated[UploadFile, File(...)],
    callback_url: CallBackUrlDep,
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ls_client: LaunchSystemClientDep,
    background_tasks: BackgroundTasks,
    entity_type: Annotated[str, Form(...)] = "EMCellMesh",
) -> MeshRegistrationResponse:
    if entity_type != "EMCellMesh":
        msg_type = f"Unsupported entity type: '{entity_type}'. Only 'EMCellMesh' is allowed."
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": msg_type,
            },
        )

    try:
        entity_uuid = UUID(entity_id)
    except ValueError as err:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Invalid entity_id format: '{entity_id}'. Must be a valid UUID.",
            },
        ) from err

    temp_obj_path = None

    try:
        temp_obj_path = _save_upload_to_tempfile(file, ".obj")

        await run_in_threadpool(validate_mesh_reader, temp_obj_path)

        obj_asset_id = await run_in_threadpool(
            _register_obj_asset,
            client,
            entity_uuid,
            pathlib.Path(temp_obj_path),
        )

        config_id = await run_in_threadpool(
            _create_lod_task_config,
            client,
            entity_uuid,
            obj_asset_id,
        )

        task_definition = TASK_DEFINITIONS[TaskType.mesh_lod_generation]

        project_context = _ensure_project_context(client)

        task_info = await run_in_threadpool(
            task_service.submit_task_job,
            db_client=client,
            ls_client=ls_client,
            callback_url=callback_url,
            config_id=config_id,
            project_context=project_context,
            task_definition=task_definition,
            callbacks=[],
        )

        background_tasks.add_task(_cleanup_temp_file, temp_obj_path)

        return MeshRegistrationResponse(
            entity_id=str(entity_uuid),
            obj_asset_id=str(obj_asset_id),
            task_job_id=str(task_info.job_id),
            status="pending",
        )

    except HTTPException:
        if temp_obj_path:
            _cleanup_temp_file(temp_obj_path)
        raise

    except BaseException as exc:
        L.error(f"Unexpected error during mesh registration: {exc!s}")

        if temp_obj_path:
            _cleanup_temp_file(temp_obj_path)

        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"An unexpected error occurred: {exc!s}",
            },
        ) from exc

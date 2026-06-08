"""Endpoint: register an EM-cell OBJ mesh and dispatch LOD generation as a task.

Pipeline
--------
1. Validate the uploaded .obj file (reuses validate_mesh_reader from mesh_validation).
2. Upload the raw OBJ as an asset attached to the existing EMCellMesh entity.
3. Create a TaskConfig entity encoding the LOD generation inputs.
4. Submit a mesh_lod_generation task job via the launch-system.
5. Return a structured response with the OBJ asset ID and the launched job ID.
"""

import json
import pathlib
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk.client
from entitysdk.exception import EntitySDKError
from entitysdk.models import EMCellMesh, TaskConfig
from entitysdk.types import AssetLabel, ContentType, TaskConfigType
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.dependencies.callback import CallBackUrlDep
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.mesh_validation import (
    MAX_FILE_SIZE,
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


def _register_obj_asset(
    client: entitysdk.client.Client,
    entity_id: UUID,
    obj_path: pathlib.Path,
) -> str:
    """Upload raw OBJ file as an asset on the EMCellMesh entity."""
    L.info(f"Uploading OBJ asset for entity {entity_id} …")
    try:
        with obj_path.open("rb") as f:
            file_content = f.read()

        asset = client.upload_content(
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_content=file_content,
            file_name=obj_path.name,
            file_content_type=ContentType.application_octet_stream,
            asset_label=AssetLabel.mesh_lod_generation__input_mesh,
        )
        L.info(f"OBJ asset uploaded successfully: {asset.path}")
    except EntitySDKError as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"Failed to upload OBJ asset to entitysdk: {exc}",
            },
        ) from exc
    else:
        return asset.path


def _create_lod_task_config(
    client: entitysdk.client.Client,
    entity_id: UUID,
    obj_asset_id: str,
) -> UUID:
    """Create a TaskConfig entity encoding the LOD generation inputs."""
    L.info(f"Creating LOD generation TaskConfig for entity {entity_id} …")
    config_payload = json.dumps(
        {
            "entity_id": str(entity_id),
            "obj_asset_id": obj_asset_id,
        }
    ).encode()

    try:
        task_config_instance = TaskConfig(
            task_config_type=TaskConfigType.mesh_lod_generation__config,
            meta={},
        )
        config_entity = client.register_entity(task_config_instance)

        if config_entity.id is None:
            msg = "Registered TaskConfig entity has no valid ID."
            raise ValueError(msg)

        client.upload_content(
            entity_id=config_entity.id,
            entity_type=TaskConfig,
            file_content=config_payload,
            file_name="config.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.mesh_lod_generation__config,
        )
    except EntitySDKError as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"LOD TaskConfig creation failed: {exc}",
            },
        ) from exc

    L.info(f"LOD TaskConfig created: {config_entity.id}")
    return config_entity.id


def _ensure_project_context(client: entitysdk.client.Client) -> None:
    """Check that the project context exists, abstracting the raise statement."""
    if client.project_context is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Client project context is missing.",
        )


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
        temp_obj_path = await _save_upload_to_tempfile(file, max_size=MAX_FILE_SIZE)

        await run_in_threadpool(validate_mesh_reader, temp_obj_path)

        obj_asset_id = await run_in_threadpool(
            _register_obj_asset, client, entity_uuid, pathlib.Path(temp_obj_path)
        )

        config_id = await run_in_threadpool(
            _create_lod_task_config, client, entity_uuid, obj_asset_id
        )

        task_definition = TASK_DEFINITIONS[TaskType.mesh_lod_generation]

        _ensure_project_context(client)

        task_info = await run_in_threadpool(
            task_service.submit_task_job,
            db_client=client,
            ls_client=ls_client,
            callback_url=callback_url,
            config_id=config_id,
            project_context=client.project_context,
            task_definition=task_definition,
            callbacks=[],
        )

        background_tasks.add_task(_cleanup_temp_file, temp_obj_path)

        return MeshRegistrationResponse(
            entity_id=str(entity_uuid),
            obj_asset_id=obj_asset_id,
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

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
import tempfile
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk
import entitysdk.client
from entitysdk.exception import EntitySDKError
from entitysdk.models import EMCellMesh, TaskConfig
from entitysdk.types import AssetLabel, ContentType, TaskConfigType

# FIX: Added BackgroundTasks to imports
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.dependencies.accounting import AccountingSessionFactoryDep
from app.dependencies.auth import UserContextWithProjectIdDep
from app.dependencies.callback import CallBackUrlDep
from app.dependencies.compute_cell import ComputeCellDep
from app.dependencies.entitysdk import get_client
from app.dependencies.launch_system import LaunchSystemClientDep
from app.endpoints.mesh_validation import (
    MAX_FILE_SIZE,
    FileTooLargeError,
    _cleanup_temp_file,
    _save_upload_to_tempfile,
    validate_mesh_reader,
)
from app.errors import ApiErrorCode
from app.logger import L
from app.mappings import TASK_DEFINITIONS
from app.services import accounting as accounting_service, task as task_service
from app.types import TaskType

router = APIRouter(
    prefix="/declared",
    tags=["declared"],
    dependencies=[Depends(get_client)],
)


class MeshRegistrationResponse(BaseModel):
    """Schema returned after a successful mesh registration."""

    entity_id: str
    obj_asset_id: str
    task_job_id: str
    status: str


def _validate_entity_id(entity_id_str: str) -> UUID:
    """Parse and return a UUID, raising 400 on malformed input."""
    try:
        return UUID(entity_id_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Invalid entity_id '{entity_id_str}': not a valid UUID.",
            },
        ) from exc


def _validate_obj_extension(filename: str | None) -> None:
    """Raise 400 if the uploaded file is not an .obj."""
    ext = pathlib.Path(filename).suffix.lower() if filename else ""
    if ext != ".obj":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid file extension. Must be .obj",
            },
        )


def _preflight_size_check(file: UploadFile) -> None:
    """Fast-path size guard using the Content-Length header when available."""
    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        L.error(f"Mesh upload rejected: file too large (reported size {file.size} B).")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        )


def _register_obj_asset(
    client: entitysdk.client.Client,
    entity_id: UUID,
    obj_path: pathlib.Path,
) -> str:
    """Upload the raw OBJ file as an asset on the given EMCellMesh entity."""
    L.info(f"Uploading original OBJ asset for entity {entity_id} …")
    try:
        asset = client.upload_file(
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_path=obj_path,
            file_content_type=ContentType.application_obj,
            asset_label=AssetLabel.cell_surface_mesh,
        )
    except EntitySDKError as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"OBJ asset registration failed: {exc}",
            },
        ) from exc

    L.info(f"OBJ asset registered: {asset.id}")
    return str(asset.id)


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
        config_entity = client.register_entity(entity_type=TaskConfig)
        client.upload_content(
            entity_id=config_entity.id,
            entity_type=TaskConfig,
            file_content=config_payload,
            file_name="config.json",
            file_content_type=ContentType.application_json,
            asset_label=TaskConfigType.mesh_lod_generation__config,
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


@router.post(
    "/register-mesh",
    summary="Register an EM-cell OBJ mesh and dispatch LOD generation as a task.",
    description=(
        "Accepts an .obj file and the ID of an existing EMCellMesh entity. "
        "Registers the OBJ as the primary surface-mesh asset, then submits an "
        "asynchronous mesh_lod_generation task..."
    ),
)
async def mesh_registration(
    file: Annotated[UploadFile, File(description="OBJ mesh file to upload (.obj)")],
    client: Annotated[entitysdk.client.Client, Depends(get_client)],
    ls_client: LaunchSystemClientDep,
    callback_url: CallBackUrlDep,
    user_context: UserContextWithProjectIdDep,
    compute_cell: ComputeCellDep,
    accounting_factory: AccountingSessionFactoryDep,
    background_tasks: BackgroundTasks,
    entity_id: Annotated[
        str, Form(description="UUID of the existing EMCellMesh entity to attach assets to")
    ],
) -> MeshRegistrationResponse:
    """Register an OBJ mesh and submit an async LOD generation task."""
    _validate_obj_extension(file.filename)
    _preflight_size_check(file)
    entity_uuid = _validate_entity_id(entity_id)

    temp_obj_path = ""
    try:
        temp_obj_path = await run_in_threadpool(_save_upload_to_tempfile, file, suffix=".obj")

        if pathlib.Path(temp_obj_path).stat().st_size == 0:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": "Uploaded file is empty.",
                },
            )

        await run_in_threadpool(validate_mesh_reader, temp_obj_path)

        obj_asset_id = await run_in_threadpool(
            _register_obj_asset, client, entity_uuid, temp_obj_path
        )

        config_id = await run_in_threadpool(
            _create_lod_task_config, client, entity_uuid, obj_asset_id
        )

        task_definition = TASK_DEFINITIONS[TaskType.mesh_lod_generation]

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
    except Exception as exc:
        L.error(f"Unexpected error during mesh registration: {exc!s}")
        if temp_obj_path:
            _cleanup_temp_file(temp_obj_path)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": "INTERNAL_ERROR",
                "detail": f"Internal server error: {exc!s}",
            },
        ) from exc

import json
import pathlib
from http import HTTPStatus
from typing import Annotated
from uuid import UUID

import entitysdk.client
import pylmesh
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

_SUPPORTED_MESH_FORMATS = {"obj", "glb"}


class MeshRegistrationResponse(BaseModel):
    entity_id: str
    glb_asset_id: str
    task_job_id: str
    status: str


def _require_uuid(value: UUID | None, msg: str) -> UUID:
    if value is None:
        raise ValueError(msg)
    return value


def _convert_obj_to_glb(obj_path: pathlib.Path, glb_path: pathlib.Path) -> None:
    L.info(f"Converting OBJ to GLB: {obj_path} -> {glb_path}")
    mesh = pylmesh.load(str(obj_path))
    pylmesh.save(str(glb_path), mesh)


def _register_glb_asset(
    client: entitysdk.client.Client,
    entity_id: UUID,
    glb_path: pathlib.Path,
) -> UUID:
    L.info(f"Uploading GLB asset for entity {entity_id} …")

    try:
        with glb_path.open("rb") as f:
            file_content = f.read()

        asset = client.upload_content(
            entity_id=entity_id,
            entity_type=EMCellMesh,
            file_content=file_content,
            file_name=glb_path.name,
            file_content_type=ContentType.model_gltf_binary,
            asset_label=AssetLabel.cell_surface_mesh,
        )

        asset_id = _require_uuid(
            asset.id,
            "Uploaded GLB asset has no valid ID.",
        )

        L.info(f"GLB asset uploaded successfully: {asset_id}")

    except (EntitySDKError, ValueError) as exc:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.ENTITYSDK_API_FAILURE,
                "detail": f"Failed to upload GLB asset to entitysdk: {exc}",
            },
        ) from exc

    return asset_id


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
            "Uploaded OBJ asset has no valid ID.",
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
    mesh_asset_id: UUID,
    mesh_format: str,
) -> UUID:
    L.info(f"Creating LOD generation TaskConfig for entity {entity_id} …")

    config_payload = json.dumps(
        {
            "type": "MeshLodGenerationSingleConfig",
            "entity_id": str(entity_id),
            "mesh_asset_id": str(mesh_asset_id),
            "mesh_format": mesh_format,
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

        config_asset = client.upload_content(
            entity_id=config_entity_id,
            entity_type=TaskConfig,
            file_content=config_payload,
            file_name="config.json",
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.task_config,
        )

        _require_uuid(
            config_asset.id,
            "Uploaded config asset has no valid ID.",
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


def _detect_mesh_format(filename: str) -> str:
    suffix = pathlib.Path(filename).suffix.lower()
    if suffix == ".obj":
        return "obj"
    if suffix == ".glb":
        return "glb"
    return ""


def _validate_entity_type(entity_type: str) -> None:
    if entity_type != "EMCellMesh":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": (
                    f"Unsupported entity type: '{entity_type}'. Only 'EMCellMesh' is allowed."
                ),
            },
        )


def _validate_mesh_format(filename: str) -> str:
    mesh_format = _detect_mesh_format(filename)
    if mesh_format not in _SUPPORTED_MESH_FORMATS:
        suffix = pathlib.Path(filename).suffix
        msg = f"Unsupported mesh file format '{suffix}'. Only .obj and .glb are accepted."
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={"code": ApiErrorCode.INVALID_REQUEST, "detail": msg},
        )
    return mesh_format


def _parse_entity_uuid(entity_id: str) -> UUID:
    try:
        return UUID(entity_id)
    except ValueError as err:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Invalid entity_id format: '{entity_id}'. Must be a valid UUID.",
            },
        ) from err


def _cleanup_temps(*paths: str | None) -> None:
    for path in paths:
        if path:
            _cleanup_temp_file(path)


async def _prepare_mesh_assets(
    client: entitysdk.client.Client,
    entity_uuid: UUID,
    temp_mesh_path: str,
    mesh_format: str,
) -> tuple[UUID, UUID, str, str | None]:
    if mesh_format == "obj":
        glb_path = pathlib.Path(temp_mesh_path).with_suffix(".glb")
        temp_glb_path = str(glb_path)
        await run_in_threadpool(
            _convert_obj_to_glb,
            pathlib.Path(temp_mesh_path),
            glb_path,
        )
        glb_asset_id = await run_in_threadpool(
            _register_glb_asset,
            client,
            entity_uuid,
            glb_path,
        )
        lod_mesh_asset_id = await run_in_threadpool(
            _register_obj_asset,
            client,
            entity_uuid,
            pathlib.Path(temp_mesh_path),
        )
        return glb_asset_id, lod_mesh_asset_id, "obj", temp_glb_path
    glb_asset_id = await run_in_threadpool(
        _register_glb_asset,
        client,
        entity_uuid,
        pathlib.Path(temp_mesh_path),
    )
    return glb_asset_id, glb_asset_id, "glb", None


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
    _validate_entity_type(entity_type)
    mesh_format = _validate_mesh_format(file.filename or "")
    entity_uuid = _parse_entity_uuid(entity_id)

    temp_mesh_path = None
    temp_glb_path = None

    try:
        temp_mesh_path = _save_upload_to_tempfile(file, f".{mesh_format}")
        await run_in_threadpool(validate_mesh_reader, temp_mesh_path)

        (
            glb_asset_id,
            lod_mesh_asset_id,
            lod_mesh_format,
            temp_glb_path,
        ) = await _prepare_mesh_assets(client, entity_uuid, temp_mesh_path, mesh_format)

        config_id = await run_in_threadpool(
            _create_lod_task_config,
            client,
            entity_uuid,
            lod_mesh_asset_id,
            lod_mesh_format,
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

        background_tasks.add_task(_cleanup_temps, temp_mesh_path, temp_glb_path)

        return MeshRegistrationResponse(
            entity_id=str(entity_uuid),
            glb_asset_id=str(glb_asset_id),
            task_job_id=str(task_info.job_id),
            status="pending",
        )

    except HTTPException:
        _cleanup_temps(temp_mesh_path, temp_glb_path)
        raise

    except BaseException as exc:
        L.error(f"Unexpected error during mesh registration: {exc!s}")
        _cleanup_temps(temp_mesh_path, temp_glb_path)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.INTERNAL_ERROR,
                "detail": f"An unexpected error occurred: {exc!s}",
            },
        ) from exc

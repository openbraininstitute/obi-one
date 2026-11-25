import tempfile
from http import HTTPStatus
from pathlib import Path
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.types import (
    ActivityStatus,
    AssetStatus,
    EntityLifecycleStatus,
    TaskActivityType,
    TaskConfigType,
)
from fastapi import APIRouter, Depends

from app.dependencies.auth import UserContextWithProjectIdDep, user_verified
from app.dependencies.callback import CallBackUrlDep
from app.dependencies.compute_cell import ComputeCellDep
from app.dependencies.entitysdk import DatabaseClientDep
from app.dependencies.launch_system import LaunchSystemClientDep
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.mappings import get_launchable_task_definition
from app.schemas.task import TaskLaunchInfo
from app.services import task as task_service
from app.types import TaskType
from obi_one.core.serialization_constants import COORDINATE_CONFIG_FILENAME
from obi_one.db_sdk import db_sdk
from obi_one.scientific.tasks.em_cell_mesh_conversion.config import (
    EMCellMeshConversionSingleConfig,
)
from obi_one.scientific.tasks.em_cell_mesh_conversion.lifecycle import (
    glb_assets,
    obj_assets,
    settle_failed_conversion,
)

router = APIRouter(
    prefix="/declared/em-cell-mesh",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)

UNFINISHED_ACTIVITY_STATUSES = {
    ActivityStatus.created,
    ActivityStatus.pending,
    ActivityStatus.running,
}


def _refuse(message: str) -> ApiError:
    return ApiError(
        message=message,
        error_code=ApiErrorCode.INVALID_REQUEST,
        http_status_code=HTTPStatus.CONFLICT,
    )


def _check_convertible(db_client: entitysdk.Client, mesh: models.EMCellMesh) -> None:
    if mesh.lifecycle_status != EntityLifecycleStatus.draft:
        msg = f"Only a draft mesh is converted; this one is {mesh.lifecycle_status}."
        raise _refuse(msg)
    if glb_assets(mesh):
        msg = "The mesh already has a GLB surface mesh."
        raise _refuse(msg)
    objs = obj_assets(mesh)
    if len(objs) != 1 or objs[0].status != AssetStatus.created:
        msg = "The mesh needs exactly one fully uploaded OBJ surface mesh."
        raise _refuse(msg)

    conversions = db_client.search_entity(
        entity_type=models.TaskActivity,
        query={
            "used__id": str(mesh.id),
            "task_activity_type": TaskActivityType.em_cell_mesh_conversion__execution,
        },
    )
    if any(activity.status in UNFINISHED_ACTIVITY_STATUSES for activity in conversions):
        msg = "A conversion of this mesh is already pending or running."
        raise _refuse(msg)


def _register_config(db_client: entitysdk.Client, mesh: models.EMCellMesh) -> models.TaskConfig:
    config = EMCellMeshConversionSingleConfig(em_cell_mesh_id=mesh.id)
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_path = Path(tmp_dir) / COORDINATE_CONFIG_FILENAME
        config_path.write_text(config.model_dump_json())
        task_config, _ = db_sdk.register_task_config_with_asset(
            client=db_client,
            name=f"EM cell mesh conversion {mesh.name}",
            description=f"OBJ to GLB conversion of EM cell mesh {mesh.id}",
            task_config_type=TaskConfigType.em_cell_mesh_conversion__config,
            multiple_value_parameters_dictionary={},
            input_entities=[mesh],  # ty:ignore[invalid-argument-type]
            task_config_file_path=config_path,
        )
    return task_config


@router.post(
    "/{entity_id}/convert",
    summary="Convert the OBJ surface mesh of a draft EM cell mesh to GLB.",
    description=(
        "Launches a free task that converts the mesh's OBJ to a Draco GLB, deletes the OBJ and"
        " sets the mesh to active. On failure the OBJ is deleted and the mesh disqualified."
    ),
)
def convert_em_cell_mesh_endpoint(
    entity_id: UUID,
    db_client: DatabaseClientDep,
    ls_client: LaunchSystemClientDep,
    callback_url: CallBackUrlDep,
    compute_cell: ComputeCellDep,
    _user_context: UserContextWithProjectIdDep,
) -> TaskLaunchInfo:
    mesh = db_client.get_entity(entity_id=entity_id, entity_type=models.EMCellMesh)
    _check_convertible(db_client, mesh)

    task_definition = get_launchable_task_definition(TaskType.em_cell_mesh_conversion)
    task_definition = task_definition.model_copy(
        update={
            "resources": task_service.apply_placement_type(
                task_definition.resources.model_copy(update={"compute_cell": compute_cell}),
                compute_cell,
            )
        }
    )
    task_config = _register_config(db_client, mesh)
    try:
        return task_service.submit_task_job(
            db_client=db_client,
            ls_client=ls_client,
            callback_url=callback_url,
            config_id=task_config.id,
            project_context=db_client.project_context,  # ty:ignore[invalid-argument-type]
            task_definition=task_definition,
            callbacks=[],
            extra_used=[mesh],
        )
    except Exception as exc:
        L.exception(f"Failed to submit the conversion of EM cell mesh {entity_id}")
        settle_failed_conversion(db_client, entity_id)
        raise ApiError(
            message="Failed to submit the conversion task",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=ApiErrorCode.INTERNAL_ERROR,
        ) from exc

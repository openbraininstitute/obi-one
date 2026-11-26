from http import HTTPStatus
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.types import AssetStatus, EntityLifecycleStatus
from fastapi import APIRouter, Depends

from app.dependencies.auth import UserContextWithProjectIdDep, user_verified
from app.dependencies.callback import CallBackUrlDep
from app.dependencies.compute_cell import ComputeCellDep
from app.dependencies.entitysdk import DatabaseClientDep
from app.dependencies.launch_system import LaunchSystemClientDep
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.mappings import get_launchable_task_definition
from app.schemas.task import TaskLaunchInfo, TaskLaunchSubmit
from app.services import task as task_service
from app.types import TaskType
from obi_one.db_sdk.em_cell_mesh import (
    glb_assets,
    has_unfinished_conversion,
    obj_assets,
    register_conversion_config,
    settle_failed_conversion,
)

router = APIRouter(
    prefix="/declared/em-cell-mesh",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)


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
    if has_unfinished_conversion(db_client, mesh.id):
        msg = "A conversion of this mesh is already pending or running."
        raise _refuse(msg)


def _settle_unless_submitted(db_client: entitysdk.Client, mesh_id: UUID) -> None:
    """Settles the mesh only when no conversion job of it can be running.

    An unfinished activity means the job may have reached the launch system; that job, or the
    failure callback, settles the mesh.
    """
    try:
        if has_unfinished_conversion(db_client, mesh_id):
            L.warning(f"The conversion of EM cell mesh {mesh_id} may be running; not settling it")
            return
        settle_failed_conversion(db_client, mesh_id)
    except Exception:  # ruff: ignore[blind-except]
        L.exception(f"Could not settle EM cell mesh {mesh_id} after the failed submission")


@router.post(
    "/{entity_id}/convert",
    summary="Convert the OBJ surface mesh of a draft EM cell mesh to GLB.",
    description=(
        "Launches a free task that converts the mesh's OBJ to a Draco GLB, deletes the OBJ and"
        " sets the mesh to active. On failure the OBJ is deleted and the mesh disqualified."
        " Call it once per mesh: two calls at the same time can both launch a job."
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

    try:
        task_config = register_conversion_config(db_client, mesh)
        task_definition = get_launchable_task_definition(TaskType.em_cell_mesh_conversion)
        resources = task_service.estimate_task_resources(
            json_model=TaskLaunchSubmit(
                task_type=TaskType.em_cell_mesh_conversion, config_id=task_config.id
            ),
            db_client=db_client,
            task_definition=task_definition,
            compute_cell=compute_cell,
        )
        task_definition = task_definition.model_copy(update={"resources": resources})
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
        _settle_unless_submitted(db_client, entity_id)
        raise ApiError(
            message="Failed to submit the conversion task",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=ApiErrorCode.INTERNAL_ERROR,
        ) from exc

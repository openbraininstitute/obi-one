from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.dependencies.accounting import AccountingSessionFactoryDep
from app.dependencies.auth import UserContextWithProjectIdDep, user_verified
from app.dependencies.callback import TaskCallBackUrlDep
from app.dependencies.entitysdk import DatabaseClientDep
from app.dependencies.launchsystem import LaunchSystemClientDep
from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import (
    TaskAccountingCreate,
    TaskAccountingInfo,
    TaskCallBackSuccessRequest,
    TaskLaunchInfo,
    TaskLaunchSubmit,
)
from app.services import accounting as accounting_service, task as task_service
from app.types import TaskType

router = APIRouter(
    prefix="/declared/task",
    tags=["declared"],
    dependencies=[Depends(user_verified)],
)


@router.post(
    "/launch",
    summary="Launch a task.",
    description=(
        "Launches an obi-one task as a dedicated job on the launch-system. "
        "The type of task is determined based on the config entity provided."
    ),
)
def task_launch_endpoint(
    json_model: TaskLaunchSubmit,
    db_client: DatabaseClientDep,
    ls_client: LaunchSystemClientDep,
    callback_url: TaskCallBackUrlDep,
    user_context: UserContextWithProjectIdDep,
    accounting_factory: AccountingSessionFactoryDep,
) -> TaskLaunchInfo:
    project_context = db_client.project_context
    task_definition = TASK_DEFINITIONS[json_model.task_type]

    accounting_info = accounting_service.estimate_task_cost(
        db_client=db_client,
        config_id=json_model.config_id,
        project_context=project_context,
        task_definition=task_definition,
        accounting_factory=accounting_factory,
    )
    accounting_session = accounting_service.make_task_reservation(
        user_context=user_context,
        service_subtype=task_definition.accounting_service_subtype,
        accounting_factory=accounting_factory,
        accounting_parameters=accounting_info.parameters,
    )
    accounting_callbacks = accounting_service.generate_accounting_callbacks(
        task_type=json_model.task_type,
        accounting_job_id=accounting_session._job_id,  # noqa: SLF001
        count=accounting_info.parameters.count,
        project_id=user_context.project_id,
        virtual_lab_id=user_context.virtual_lab_id,
        callback_url=callback_url,
    )
    try:
        return task_service.submit_task_job(
            db_client=db_client,
            ls_client=ls_client,
            callback_url=callback_url,
            config_id=json_model.config_id,
            project_context=project_context,
            task_definition=TASK_DEFINITIONS[json_model.task_type],
            callbacks=accounting_callbacks,
        )
    except Exception as exc:
        accounting_session.finish(exc_type=type(exc))
        raise ApiError(
            message="Failed to submit task job",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=ApiErrorCode.INTERNAL_ERROR,
        ) from exc


@router.post(
    "/estimate",
    summary="Estimate task cost.",
    description=(
        "Estimates the cost in credits for launching an obi-one task. "
        "Takes the same parameters as /launch and returns a cost estimate."
    ),
)
def estimate_endpoint(
    json_model: TaskAccountingCreate,
    db_client: DatabaseClientDep,
    _user_context: UserContextWithProjectIdDep,  # ensure there is a project_id
    accounting_factory: AccountingSessionFactoryDep,
) -> TaskAccountingInfo:
    """Estimates the cost for launching a task."""
    return accounting_service.estimate_task_cost(
        db_client=db_client,
        config_id=json_model.config_id,
        project_context=db_client.project_context,
        accounting_factory=accounting_factory,
        task_definition=TASK_DEFINITIONS[json_model.task_type],
    )


@router.post(
    "/callback/failure",
    summary="Task failure callback",
    description=(
        "Callback endpoint to mark a task execution activity as failed. "
        "Used by the launch-system to report task failures."
    ),
)
def task_failure_endpoint(
    task_type: TaskType,
    activity_id: UUID,
    db_client: DatabaseClientDep,
    _user_context: UserContextWithProjectIdDep,
) -> None:
    task_service.handle_task_failure_callback(
        db_client=db_client,
        activity_id=activity_id,
        task_definition=TASK_DEFINITIONS[task_type],
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router.post(
    "/callback/success",
    summary="Task success callback",
    description=("Callback endpoint that is called on task success."),
)
def task_success_endpoint(
    json_model: TaskCallBackSuccessRequest,
    accounting_factory: AccountingSessionFactoryDep,
    user_context: UserContextWithProjectIdDep,
) -> None:
    task_definition = TASK_DEFINITIONS[json_model.task_type]
    accounting_service.finish_accounting_session(
        accounting_job_id=json_model.job_id,
        service_subtype=task_definition.accounting_service_subtype,
        count=json_model.count,
        project_id=user_context.project_id,
        http_client=accounting_factory._http_client,  # noqa: SLF001
    )
    return Response(status_code=HTTPStatus.NO_CONTENT)

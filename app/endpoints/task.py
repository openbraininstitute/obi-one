from http import HTTPStatus
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from app.dependencies.accounting import AccountingSessionFactoryDep
from app.dependencies.auth import UserContextWithProjectIdDep, user_verified
from app.dependencies.callback import CallBackUrlDep
from app.dependencies.entitysdk import DatabaseClientDep
from app.dependencies.launchsystem import LaunchSystemClientDep
from app.errors import ApiError, ApiErrorCode
from app.logger import L
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import (
    TaskAccountingCreate,
    TaskAccountingInfo,
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
    callback_url: CallBackUrlDep,
    user_context: UserContextWithProjectIdDep,
    accounting_factory: AccountingSessionFactoryDep,
) -> TaskLaunchInfo:
    L.info(
        f"Task launch request: task_type={json_model.task_type}, config_id={json_model.config_id}"
    )

    project_context = db_client.project_context
    task_definition = TASK_DEFINITIONS[json_model.task_type]

    accounting_session = None
    try:
        # Estimate task cost
        accounting_info = accounting_service.estimate_task_cost(
            db_client=db_client,
            config_id=json_model.config_id,
            project_context=project_context,
            task_definition=task_definition,
            accounting_factory=accounting_factory,
        )

        # Make accounting reservation
        accounting_session = accounting_service.make_task_reservation(
            user_context=user_context,
            service_subtype=task_definition.accounting_service_subtype,
            accounting_factory=accounting_factory,
            accounting_parameters=accounting_info.parameters,
        )

        # Generate accounting callbacks
        accounting_callbacks = accounting_service.generate_accounting_callbacks(
            accounting_job_id=accounting_session._job_id,  # noqa: SLF001
            service_subtype=task_definition.accounting_service_subtype,
            count=accounting_info.parameters.count,
            project_id=user_context.project_id,
        )

        # Submit task job
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
        L.error(f"Task launch failed: {exc}", exc_info=True)

        # Clean up accounting session if it was created
        if accounting_session is not None:
            try:
                accounting_session.finish(exc_type=type(exc))
            except Exception as cleanup_exc:  # noqa: BLE001
                L.error(f"Failed to clean up accounting session: {cleanup_exc}", exc_info=True)

        raise ApiError(
            message=f"Failed to launch task: {exc}",
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
    L.info(f"Task failure callback received: task_type={task_type}, activity_id={activity_id}")

    try:
        task_service.handle_task_failure_callback(
            db_client=db_client,
            activity_id=activity_id,
            task_definition=TASK_DEFINITIONS[task_type],
        )
        L.info(f"Task failure callback processed successfully for activity {activity_id}")
    except Exception as exc:
        L.error(
            f"Failed to process task failure callback for activity {activity_id}: {exc}",
            exc_info=True,
        )
        raise ApiError(
            message=f"Failed to process task failure callback: {exc}",
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            error_code=ApiErrorCode.INTERNAL_ERROR,
        ) from exc

    return Response(status_code=HTTPStatus.NO_CONTENT)

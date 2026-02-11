from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.mappings import TASK_DEFINITIONS
from app.schemas.accounting import AccountingParameters
from app.schemas.callback import CallBack, CallBackAction, CallBackEvent, HttpRequestCallBackConfig
from app.schemas.task import TaskAccountingInfo, TaskLaunchInfo
from app.types import TaskType


@pytest.fixture
def callbacks():
    config = HttpRequestCallBackConfig(
        url="http://failure",
        method="POST",
    )
    return [
        CallBack(
            event_type=CallBackEvent.job_on_failure,
            action_type=CallBackAction.http_request_with_token,
            config=config,
        )
    ]


@pytest.mark.parametrize("task_type", TaskType)
def test_task_launch_success(
    client,
    callbacks,
    task_type,
):
    job_id = uuid4()
    config_id = uuid4()
    activity_id = uuid4()
    task_definition = TASK_DEFINITIONS[task_type]
    accounting_session = SimpleNamespace(_job_id="job-123", finish=Mock())
    accounting_parameters = AccountingParameters(
        count=10,
        service_subtype=task_definition.accounting_service_subtype,
    )
    task_accounting_info = TaskAccountingInfo(
        cost=123.4,
        config_id=config_id,
        parameters=accounting_parameters,
        task_type=task_type,
    )
    task_launch_info = TaskLaunchInfo(
        job_id=job_id,
        config_id=config_id,
        task_type=task_type,
        activity_id=activity_id,
    )
    with (
        patch(
            "app.services.accounting.estimate_task_cost",
            return_value=task_accounting_info,
            autospec=True,
        ),
        patch(
            "app.services.accounting.make_task_reservation",
            return_value=accounting_session,
            autospec=True,
        ),
        patch(
            "app.services.accounting.generate_accounting_callbacks",
            return_value=callbacks,
            autospec=True,
        ),
        patch(
            "app.services.task.submit_task_job",
            return_value=task_launch_info,
            autospec=True,
        ) as patched_task_job,
    ):
        data = (
            client.post(
                url="/declared/task/launch",
                json={
                    "task_type": task_type,
                    "config_id": str(config_id),
                },
            )
            .raise_for_status()
            .json()
        )

        assert data["job_id"] == str(job_id)
        assert data["config_id"] == str(config_id)
        assert data["activity_id"] == str(activity_id)
        assert data["task_type"] == task_type

        patched_task_job.side_effect = RuntimeError("submit failed")

        resp = client.post(
            url="/declared/task/launch",
            json={
                "task_type": task_type,
                "config_id": str(config_id),
            },
        )
        assert resp.status_code == 500

        accounting_session.finish.assert_called_once_with(exc_type=RuntimeError)


@pytest.mark.parametrize("task_type", TaskType)
def test_task_estimate(client, task_type):
    config_id = uuid4()

    task_definition = TASK_DEFINITIONS[task_type]
    accounting_parameters = AccountingParameters(
        count=10,
        service_subtype=task_definition.accounting_service_subtype,
    )
    task_accounting_info = TaskAccountingInfo(
        cost=123.4,
        config_id=config_id,
        parameters=accounting_parameters,
        task_type=task_type,
    )
    with patch(
        "app.services.accounting.estimate_task_cost",
        return_value=task_accounting_info,
        autospec=True,
    ):
        data = (
            client.post(
                url="/declared/task/estimate",
                json={
                    "task_type": task_type,
                    "config_id": str(config_id),
                },
            )
            .raise_for_status()
            .json()
        )

    assert data["task_type"] == task_type
    assert data["config_id"] == str(config_id)
    assert data["cost"] == 123.4
    assert data["parameters"]["service_subtype"] == task_definition.accounting_service_subtype
    assert data["parameters"]["count"] == 10


@pytest.mark.parametrize("task_type", TaskType)
def test_task_failure_endpoint(client, task_type):
    activity_id = uuid4()

    with patch("app.services.task.handle_task_failure_callback", autospec=True):
        client.post(
            url="/declared/task/callback/failure",
            params={
                "task_type": task_type,
                "activity_id": str(activity_id),
            },
        ).raise_for_status()

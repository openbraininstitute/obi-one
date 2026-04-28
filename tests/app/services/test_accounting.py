import json
from http import HTTPStatus
from unittest.mock import ANY, patch
from uuid import UUID, uuid4

import entitysdk
import httpx
import pytest
from fastapi import HTTPException
from obp_accounting_sdk.constants import ServiceSubtype
from obp_accounting_sdk.errors import BaseAccountingError, InsufficientFundsError

from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.accounting import AccountingParameters
from app.schemas.callback import CallBackAction, CallBackEvent
from app.schemas.task import TaskAccountingInfo
from app.services import accounting as test_module
from app.types import TaskType

from tests.utils import PROJECT_ID, VIRTUAL_LAB_ID


@pytest.fixture
def db_client():
    """Mock entitysdk Client with spec."""
    return entitysdk.Client(api_url="http://my-url", token_manager="my-token")  # noqa: S106


@pytest.fixture
def accounting_parameters():
    return AccountingParameters(count=10, service_subtype=ServiceSubtype.SMALL_SIM)


@pytest.fixture
def task_definition():
    return TASK_DEFINITIONS[TaskType.circuit_simulation]


def test_make_task_reservation_success(user_context_user_1, accounting_parameters):
    class FakeSession:
        job_id = uuid4()

        def make_reservation(self):
            return None

    class FakeFactory:
        def oneshot_session(self, **_kwargs):
            return FakeSession()

    session = test_module.make_task_reservation(
        user_context=user_context_user_1,
        accounting_parameters=accounting_parameters,
        accounting_factory=FakeFactory(),
    )

    assert session.job_id is not None


def test_make_task_reservation_insufficient_funds(user_context_user_1, accounting_parameters):
    class FakeSession:
        def make_reservation(self):
            raise InsufficientFundsError

    class FakeFactory:
        def oneshot_session(self, **_kwargs):
            return FakeSession()

    with pytest.raises(ApiError) as exc:
        test_module.make_task_reservation(
            user_context=user_context_user_1,
            accounting_parameters=accounting_parameters,
            accounting_factory=FakeFactory(),
        )

    err = exc.value
    assert err.http_status_code == HTTPStatus.FORBIDDEN
    assert err.error_code == ApiErrorCode.ACCOUNTING_INSUFFICIENT_FUNDS_ERROR


def test_make_task_reservation__generic_accounting_error(
    user_context_user_1, accounting_parameters
):
    class FakeSession:
        def make_reservation(self):
            msg = "Internal accounting error"
            raise BaseAccountingError(msg)

    class FakeFactory:
        def oneshot_session(self, **_kwargs):
            return FakeSession()

    with pytest.raises(ApiError) as exc:
        test_module.make_task_reservation(
            user_context=user_context_user_1,
            accounting_parameters=accounting_parameters,
            accounting_factory=FakeFactory(),
        )

    assert exc.value.http_status_code == HTTPStatus.BAD_GATEWAY
    assert exc.value.error_code == ApiErrorCode.ACCOUNTING_GENERIC_ERROR


def test_estimate_task_cost(project_context, accounting_parameters, task_definition):
    class FakeFactory:
        def estimate_oneshot_cost(self, **_kwargs):
            return 100.0

    with patch(
        "app.services.accounting._evaluate_accounting_parameters",
        return_value=accounting_parameters,
    ):
        info = test_module.estimate_task_cost(
            db_client=None,
            config_id=uuid4(),
            task_definition=task_definition,
            project_context=project_context,
            accounting_factory=FakeFactory(),
        )

    assert isinstance(info, TaskAccountingInfo)
    assert info.cost == 100.0
    assert info.parameters == accounting_parameters


def test_evaluate_circuit_simulation_parameters(db_client, httpx_mock):
    config_id = uuid4()
    entity_id = uuid4()
    simulation_campaign_id = uuid4()

    httpx_mock.add_response(
        url=f"http://my-url/simulation/{config_id}",
        method="GET",
        json={
            "id": str(config_id),
            "simulation_campaign_id": str(simulation_campaign_id),
            "entity_id": str(entity_id),
            "number_neurons": 3,
            "scan_parameters": {},
        },
    )
    httpx_mock.add_response(
        url=f"http://my-url/circuit/{entity_id}",
        method="GET",
        json={
            "id": str(entity_id),
            "number_neurons": 3,
            "number_synapses": 10,
            "number_connections": 12,
            "scale": "small",
            "build_category": "computational_model",
        },
    )

    res = test_module._evaluate_circuit_simulation_parameters(
        db_client=db_client,
        simulation_id=config_id,
    )

    assert res.service_subtype == ServiceSubtype.SMALL_SIM
    assert res.count == 3


def test_evaluate_circuit_simulation_parameters__error(db_client, httpx_mock):
    config_id = uuid4()
    entity_id = uuid4()
    simulation_campaign_id = uuid4()

    httpx_mock.add_response(
        url=f"http://my-url/simulation/{config_id}",
        method="GET",
        json={
            "id": str(config_id),
            "simulation_campaign_id": str(simulation_campaign_id),
            "entity_id": str(entity_id),
            "number_neurons": 3,
            "scan_parameters": {},
        },
    )
    httpx_mock.add_response(
        url=f"http://my-url/circuit/{entity_id}",
        method="GET",
        json={
            "id": str(entity_id),
            "number_neurons": 3,
            "number_synapses": 10,
            "number_connections": 12,
            "scale": "pair",
            "build_category": "computational_model",
        },
    )

    with pytest.raises(HTTPException, match="Unsupported circuit scale"):
        test_module._evaluate_circuit_simulation_parameters(
            db_client=db_client,
            simulation_id=config_id,
        )


@pytest.mark.parametrize("task_type", TaskType)
def test_evaluate_accounting_parameters(db_client, task_type, accounting_parameters):
    config_id = uuid4()
    task_definition = TASK_DEFINITIONS[task_type]

    expected_subtype = {
        TaskType.circuit_extraction: ServiceSubtype.CIRCUIT_EXTRACTION,
        TaskType.circuit_simulation: ServiceSubtype.SMALL_SIM,
        TaskType.ion_channel_model_simulation_execution: ServiceSubtype.ION_CHANNEL_SIM,
        TaskType.morphology_skeletonization: ServiceSubtype.NEURON_MESH_SKELETONIZATION,
        TaskType.em_synapse_mapping: ServiceSubtype.SMALL_CIRCUIT_SIM,
    }
    expected_count = {
        TaskType.circuit_extraction: 321,
        TaskType.circuit_simulation: 10,
        TaskType.ion_channel_model_simulation_execution: 1,
        TaskType.morphology_skeletonization: 800,
        TaskType.em_synapse_mapping: 1,
    }

    with (
        patch(
            "app.services.accounting._evaluate_circuit_simulation_parameters",
            return_value=accounting_parameters,
            autospec=True,
        ),
        patch(
            "app.services.accounting.estimate_skeletonization_count",
            return_value=expected_count[TaskType.morphology_skeletonization],
        ),
        patch(
            "app.services.accounting.estimate_circuit_extraction_count",
            return_value=expected_count[TaskType.circuit_extraction],
        ),
    ):
        res = test_module._evaluate_accounting_parameters(
            db_client=db_client,
            config_id=config_id,
            task_definition=task_definition,
        )
        assert res.service_subtype == expected_subtype[task_type]
        assert res.count == expected_count[task_type]


def test_generate_accounting_callbacks(accounting_parameters):
    job_id = uuid4()

    res = test_module.generate_accounting_callbacks(
        task_type=TaskType.circuit_extraction,
        accounting_job_id=job_id,
        accounting_parameters=accounting_parameters,
        project_id=UUID(PROJECT_ID),
        virtual_lab_id=UUID(VIRTUAL_LAB_ID),
        callback_url="my-callback",
    )

    assert len(res) == 2

    failure_callback, success_callback = res

    assert failure_callback.event_type == CallBackEvent.job_on_failure
    assert failure_callback.action_type == CallBackAction.http_request_with_token

    assert success_callback.event_type == CallBackEvent.job_on_success
    assert success_callback.action_type == CallBackAction.http_request_with_token


def test_finish_accounting_session_success(monkeypatch, httpx_mock):
    monkeypatch.setattr(
        "app.services.accounting.settings.ACCOUNTING_BASE_URL",
        "http://accounting",
    )

    httpx_mock.add_response(
        method="POST",
        url="http://accounting/usage/oneshot",
        status_code=200,
    )

    client = httpx.Client()

    job_id = UUID(int=0)
    proj_id = UUID(int=1)

    test_module.finish_accounting_session(
        accounting_job_id=job_id,
        service_subtype="compute",
        count=3,
        project_id=proj_id,
        http_client=client,
    )

    # Assert request content
    request = httpx_mock.get_request()

    assert request.method == "POST"
    assert str(request.url) == "http://accounting/usage/oneshot"

    assert json.loads(request.content) == {
        "type": "oneshot",
        "subtype": "compute",
        "proj_id": str(proj_id),
        "count": "3",
        "job_id": str(job_id),
        "timestamp": ANY,
    }

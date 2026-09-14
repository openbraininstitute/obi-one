from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from entitysdk.types import CircuitScale

from app.errors import ApiError, ApiErrorCode
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskLaunchSubmit, TaskType
from app.services.resource_estimation import synapse_parameterization as test_module


@pytest.fixture
def task_definition():
    return TASK_DEFINITIONS[TaskType.circuit_synaptic_physiology_assignment]


@pytest.fixture
def json_model():
    return TaskLaunchSubmit(
        task_type=TaskType.circuit_synaptic_physiology_assignment,
        config_id=uuid4(),
    )


def _db_client_returning_scale(scale):
    """Mock db_client whose get_entity yields the config, then a circuit of the given scale."""
    circuit_id = uuid4()
    config = SimpleNamespace(inputs=[SimpleNamespace(id=circuit_id)])
    circuit = SimpleNamespace(id=circuit_id, scale=scale)
    db_client = Mock()
    db_client.get_entity.side_effect = [config, circuit]
    return db_client


@pytest.mark.parametrize(
    "scale",
    [CircuitScale.single, CircuitScale.pair, CircuitScale.small],
)
def test_supported_scale_keeps_defaults(scale, json_model, task_definition):
    """A supported scale returns the task defaults with only compute_cell stamped."""
    db_client = _db_client_returning_scale(scale)

    result = test_module.estimate_task_resources(
        json_model=json_model,
        db_client=db_client,
        task_definition=task_definition,
        compute_cell="cell_b",
    )

    assert result == task_definition.resources.model_copy(update={"compute_cell": "cell_b"})


@pytest.mark.parametrize(
    "scale",
    [
        CircuitScale.microcircuit,
        CircuitScale.region,
        CircuitScale.system,
        CircuitScale.whole_brain,
    ],
)
def test_oversized_scale_is_rejected(scale, json_model, task_definition):
    """A scale larger than 'small' raises an ApiError and does not return resources."""
    db_client = _db_client_returning_scale(scale)

    with pytest.raises(ApiError) as exc_info:
        test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_b",
        )

    assert exc_info.value.error_code == ApiErrorCode.INVALID_REQUEST
    assert exc_info.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    # The rejected scale and the supported scales are named in the message.
    assert str(scale.value) in exc_info.value.message
    for supported in ("single", "pair", "small"):
        assert supported in exc_info.value.message


def test_error_message_lists_supported_scales_from_the_constant(json_model, task_definition):
    """The message derives its supported list from SUPPORTED_CIRCUIT_SCALES, not a hardcode."""
    db_client = _db_client_returning_scale(CircuitScale.region)

    with pytest.raises(ApiError) as exc_info:
        test_module.estimate_task_resources(
            json_model=json_model,
            db_client=db_client,
            task_definition=task_definition,
            compute_cell="cell_b",
        )

    for scale in test_module.SUPPORTED_CIRCUIT_SCALES:
        assert f"'{scale.value}'" in exc_info.value.message

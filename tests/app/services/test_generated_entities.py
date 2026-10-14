from datetime import UTC, datetime
from http import HTTPStatus
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import entitysdk
import pytest
from entitysdk.common import ProjectContext
from entitysdk.types import EntityType

from app.errors import ApiError
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskGroupLegacyDefinition
from app.services import generated_entities as test_module
from app.types import TaskType
from obi_one.scientific.mappings_and_registry.config_task_map import get_task_spec_for_task_type

from tests.utils import PROJECT_ID, VIRTUAL_LAB_ID

CIRCUIT_TASK = TASK_DEFINITIONS[TaskType.circuit_single_build]
NO_OUTPUT_TASK = TASK_DEFINITIONS[TaskType.efeature_extraction]
TASK_TYPES_WITH_GENERATED_ENTITIES = [
    task_type
    for task_type, definition in TASK_DEFINITIONS.items()
    if not isinstance(definition, TaskGroupLegacyDefinition) and definition.generated_entity_types
]


def _db_client(httpx_mock, activity_id, generated):
    httpx_mock.add_response(
        url=f"http://my-url/task-activity/{activity_id}",
        method="GET",
        json={
            "id": str(activity_id),
            "status": "done",
            "start_time": datetime.now(UTC).isoformat(),
            "task_activity_type": "circuit_single_build__execution",
            "generated": [
                {"id": str(entity_id), "type": entity_type, "lifecycle_status": status}
                for entity_id, entity_type, status in generated
            ],
        },
    )
    return entitysdk.Client(
        api_url="http://my-url",
        token_manager="my-token",  # ruff: ignore[hardcoded-password-func-arg]
        project_context=ProjectContext(virtual_lab_id=VIRTUAL_LAB_ID, project_id=PROJECT_ID),
    )


class TestGetGeneratedEntityHandlers:
    def test_circuit_handler_sets_async_validation(self):
        handlers = test_module.get_generated_entity_handlers(CIRCUIT_TASK)

        assert list(handlers) == [EntityType.circuit]
        assert handlers[EntityType.circuit].task_options == {
            "circuit_validation_mode": "async_launch"
        }

    def test_types_without_handler_are_skipped(self):
        memodel_task = CIRCUIT_TASK.model_copy(
            update={"generated_entity_types": (EntityType.memodel,)}
        )

        assert test_module.get_generated_entity_handlers(memodel_task) == {}
        assert test_module.get_generated_entity_handlers(NO_OUTPUT_TASK) == {}

    @pytest.mark.parametrize("task_type", TASK_TYPES_WITH_GENERATED_ENTITIES)
    def test_task_classes_accept_the_handler_options(self, task_type):
        """The job sets the handler options as task fields, so each task needs those fields."""
        handlers = test_module.get_generated_entity_handlers(TASK_DEFINITIONS[task_type])
        task_fields = get_task_spec_for_task_type(task_type).task_cls.model_fields

        assert handlers
        for handler in handlers.values():
            assert set(handler.task_options) <= set(task_fields)


class TestHandleGeneratedEntities:
    """After a task job succeeds, its draft circuits each get a validation job."""

    @patch("app.services.circuit_launch.trigger_validation_task")
    def test_submits_validation_only_for_draft_circuits(self, mock_trigger, httpx_mock):
        activity_id = uuid4()
        draft_circuit_id = uuid4()
        mock_trigger.return_value = uuid4()
        db_client = _db_client(
            httpx_mock,
            activity_id,
            [
                (draft_circuit_id, "circuit", "draft"),
                (uuid4(), "circuit", "active"),
                (uuid4(), "memodel", "draft"),
            ],
        )
        ls_client = MagicMock()

        test_module.handle_generated_entities(
            task_definition=CIRCUIT_TASK,
            activity_id=activity_id,
            db_client=db_client,
            ls_client=ls_client,
            compute_cell="cell_a",
        )

        mock_trigger.assert_called_once_with(
            ls_client=ls_client,
            circuit_id=draft_circuit_id,
            project_id=UUID(PROJECT_ID),
            virtual_lab_id=UUID(VIRTUAL_LAB_ID),
            compute_cell="cell_a",
        )

    @patch("app.services.circuit_launch.trigger_validation_task")
    def test_raises_after_trying_every_draft(self, mock_trigger, httpx_mock):
        """One failed submission does not stop the others; the error is raised at the end."""
        activity_id = uuid4()
        failed_circuit_id = uuid4()
        mock_trigger.side_effect = [None, uuid4()]
        db_client = _db_client(
            httpx_mock,
            activity_id,
            [(failed_circuit_id, "circuit", "draft"), (uuid4(), "circuit", "draft")],
        )

        with pytest.raises(ApiError) as exc_info:
            test_module.handle_generated_entities(
                task_definition=CIRCUIT_TASK,
                activity_id=activity_id,
                db_client=db_client,
                ls_client=MagicMock(),
                compute_cell="cell_a",
            )

        assert exc_info.value.http_status_code == HTTPStatus.INTERNAL_SERVER_ERROR
        assert str(failed_circuit_id) in exc_info.value.message
        assert mock_trigger.call_count == 2

    def test_rejects_a_task_without_handlers(self):
        """The callback is only registered for tasks with a handler; anything else is a bug."""
        with pytest.raises(ApiError) as exc_info:
            test_module.handle_generated_entities(
                task_definition=NO_OUTPUT_TASK,
                activity_id=uuid4(),
                db_client=MagicMock(),
                ls_client=MagicMock(),
                compute_cell="cell_a",
            )

        assert exc_info.value.http_status_code == HTTPStatus.INTERNAL_SERVER_ERROR

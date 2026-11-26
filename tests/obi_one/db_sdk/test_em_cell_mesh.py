import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from entitysdk.models import TaskActivity
from entitysdk.types import ActivityStatus, TaskActivityType, TaskConfigType

from obi_one.db_sdk import em_cell_mesh as test_module


class TestHasUnfinishedConversion:
    @pytest.mark.parametrize(
        ("statuses", "expected"),
        [
            ([], False),
            ([ActivityStatus.done, ActivityStatus.error], False),
            ([ActivityStatus.error, ActivityStatus.pending], True),
            ([ActivityStatus.created], True),
            ([ActivityStatus.running], True),
        ],
    )
    def test_reports_a_created_pending_or_running_conversion(self, statuses, expected):
        mesh_id = uuid4()
        db_client = Mock()
        db_client.search_entity.return_value = [SimpleNamespace(status=s) for s in statuses]

        assert test_module.has_unfinished_conversion(db_client, mesh_id) is expected
        db_client.search_entity.assert_called_once_with(
            entity_type=TaskActivity,
            query={
                "used__id": str(mesh_id),
                "task_activity_type": TaskActivityType.em_cell_mesh_conversion__execution,
            },
        )


def test_register_conversion_config_uploads_the_mesh_config():
    mesh = SimpleNamespace(id=uuid4(), name="neuron 42")
    db_client = Mock()
    task_config = SimpleNamespace(id=uuid4())
    uploaded = {}

    def register(**kwargs):
        uploaded.update(kwargs, config=json.loads(kwargs["task_config_file_path"].read_text()))
        return task_config, None

    with patch.object(test_module.db_sdk, "register_task_config_with_asset", side_effect=register):
        result = test_module.register_conversion_config(db_client, mesh)

    assert result is task_config
    assert uploaded["client"] is db_client
    assert uploaded["name"] == "EM cell mesh conversion neuron 42"
    assert uploaded["task_config_type"] == TaskConfigType.em_cell_mesh_conversion__config
    assert uploaded["input_entities"] == [mesh]
    assert uploaded["config"]["em_cell_mesh_id"] == str(mesh.id)

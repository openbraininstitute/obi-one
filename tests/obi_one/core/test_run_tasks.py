import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from obi_one.core import run_tasks as test_module
from obi_one.types import TaskType


@pytest.fixture
def db_client():
    client = MagicMock()
    client.download_content.return_value = json.dumps({"type": "X", "idx": 0}).encode("utf-8")
    client.get_entity.return_value = MagicMock()
    return client


@pytest.fixture
def mock_single_config():
    config = MagicMock()
    return config


@patch("obi_one.core.run_tasks.db_sdk.get_entity_asset_by_label")
@patch("obi_one.core.run_tasks.get_task_type")
@patch("obi_one.core.run_tasks.deserialize_obi_object_from_json_data")
def test_run_task_type_downloads_config_deserializes_sets_entity_and_executes_task(
    mock_deserialize, mock_get_task_type, mock_get_asset, db_client, mock_single_config
):
    entity_type = MagicMock()
    mock_task_cls = MagicMock()
    mock_task_instance = MagicMock()
    mock_task_cls.return_value = mock_task_instance
    mock_get_task_type.return_value = mock_task_cls
    mock_deserialize.return_value = mock_single_config
    mock_get_asset.return_value = SimpleNamespace(id="asset-1")

    test_module.run_task_type(
        TaskType.circuit_extraction,
        entity_type=entity_type,
        entity_id="ent-1",
        scan_output_root="/out",
        db_client=db_client,
        entity_cache=True,
        execution_activity_id="act-1",
    )

    mock_get_asset.assert_called_once()
    db_client.download_content.assert_called_once_with(
        entity_id="ent-1",
        entity_type=entity_type,
        asset_id="asset-1",
    )
    call_json_dict = mock_deserialize.call_args[0][0]
    assert call_json_dict["scan_output_root"] == "/out"
    assert call_json_dict["coordinate_output_root"] == Path("/out") / "0"
    db_client.get_entity.assert_called_once_with(
        entity_id="ent-1",
        entity_type=entity_type,
    )
    mock_single_config.set_single_entity.assert_called_once_with(db_client.get_entity.return_value)
    mock_get_task_type.assert_called_once_with(TaskType.circuit_extraction)
    mock_task_cls.assert_called_once_with(config=mock_single_config)
    mock_task_instance.execute.assert_called_once_with(
        db_client=db_client,
        entity_cache=True,
        execution_activity_id="act-1",
    )

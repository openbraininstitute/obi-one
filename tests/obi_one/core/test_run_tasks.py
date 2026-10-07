import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.types import AssetLabel

from obi_one_lazy.core import run_tasks as test_module
from obi_one_lazy.core.registry import TaskRegistration
from obi_one_lazy.types import TaskType


@pytest.fixture
def db_client():
    client = MagicMock()
    client.download_content.return_value = json.dumps({"type": "X", "idx": 0}).encode("utf-8")
    client.get_entity.return_value = MagicMock()
    return client


@pytest.fixture
def mock_single_config():
    return MagicMock()


@patch("obi_one_lazy.core.run_tasks.db_sdk.get_entity_asset_by_label")
@patch("obi_one_lazy.core.run_tasks.resolve_task_registration")
@patch("obi_one_lazy.core.run_tasks.deserialize_obi_object_from_json_data")
def test_run_task_type_downloads_config_deserializes_sets_entity_and_executes_task(
    mock_deserialize,
    mock_resolve,
    mock_get_asset,
    db_client,
    mock_single_config,
):
    entity_type = MagicMock()
    mock_task_cls = MagicMock()
    mock_task_instance = MagicMock()
    mock_task_cls.return_value = mock_task_instance
    mock_deserialize.return_value = mock_single_config
    mock_get_asset.return_value = SimpleNamespace(id="asset-1")
    mock_resolve.return_value = TaskRegistration(
        task_cls=mock_task_cls,
        single_config_cls=MagicMock(),
        asset_label=AssetLabel.task_config,
    )

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
    mock_resolve.assert_called_once_with(TaskType.circuit_extraction)
    mock_task_cls.assert_called_once_with(config=mock_single_config)
    mock_task_instance.execute.assert_called_once_with(
        db_client=db_client,
        entity_cache=True,
        execution_activity_id="act-1",
    )


@patch("obi_one_lazy.core.run_tasks.resolve_task_registration")
def test_run_task_type_without_asset_label_creates_default_config(
    mock_resolve,
    db_client,
):
    """When asset_label is None, creates a default config from the single config class."""
    entity_type = MagicMock()
    mock_config_cls = MagicMock()
    mock_config_instance = MagicMock()
    mock_config_cls.return_value = mock_config_instance

    mock_task_cls = MagicMock()
    mock_task_instance = MagicMock()
    mock_task_cls.return_value = mock_task_instance
    mock_resolve.return_value = TaskRegistration(
        task_cls=mock_task_cls,
        single_config_cls=mock_config_cls,
        asset_label=None,
    )

    test_module.run_task_type(
        TaskType.circuit_simulation,
        entity_type=entity_type,
        entity_id="ent-1",
        scan_output_root="/out",
        db_client=db_client,
        entity_cache=False,
        execution_activity_id="act-1",
    )

    db_client.download_content.assert_not_called()
    mock_config_cls.assert_called_once_with(scan_output_root="/out")
    mock_config_instance.set_single_entity.assert_called_once_with(
        db_client.get_entity.return_value
    )
    mock_task_cls.assert_called_once_with(config=mock_config_instance)
    mock_task_instance.execute.assert_called_once_with(
        db_client=db_client,
        entity_cache=False,
        execution_activity_id="act-1",
    )

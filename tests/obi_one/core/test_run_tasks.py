import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from obi_one.core import run_tasks as test_module
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionSingleConfig,
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.simulation_execution.neuron.circuit_simulation_execution import (
    CircuitSimulationExecutionTask,
)
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


@patch("obi_one.core.run_tasks.deserialize_obi_object_from_json_data")
@patch("obi_one.core.run_tasks.db_sdk.get_entity_asset_by_label")
def test_run_task_type_resolves_lazy_task_spec_with_asset_label(
    mock_get_asset,
    mock_deserialize,
    db_client,
):
    """Uses real ``config_task_map`` (no mock on ``get_task_spec_for_task_type``)."""
    entity_type = MagicMock()
    mock_get_asset.return_value = SimpleNamespace(id="asset-1")
    db_client.download_content.return_value = json.dumps(
        {"type": "CircuitExtractionSingleConfig", "idx": 0}
    ).encode("utf-8")
    single_config = CircuitExtractionSingleConfig.model_construct()
    mock_deserialize.return_value = single_config
    captured: dict[str, object] = {}

    def capture_execute(self, **kwargs):
        captured["task"] = self
        captured["kwargs"] = kwargs

    with patch.object(CircuitExtractionTask, "execute", capture_execute):
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
    assert isinstance(captured["task"], CircuitExtractionTask)
    assert captured["kwargs"] == {
        "db_client": db_client,
        "entity_cache": True,
        "execution_activity_id": "act-1",
    }


def test_run_task_type_resolves_lazy_task_spec_without_asset_label(db_client):
    entity_type = MagicMock()
    captured: dict[str, object] = {}

    def capture_execute(self, **kwargs):
        captured["task"] = self
        captured["kwargs"] = kwargs

    with patch.object(CircuitSimulationExecutionTask, "execute", capture_execute):
        test_module.run_task_type(
            TaskType.circuit_simulation_neurodamus_machine,
            entity_type=entity_type,
            entity_id="ent-1",
            scan_output_root="/out",
            db_client=db_client,
        )

    db_client.download_content.assert_not_called()
    assert isinstance(captured["task"], CircuitSimulationExecutionTask)
    execute_kwargs = captured["kwargs"]
    assert isinstance(execute_kwargs, dict)
    assert execute_kwargs["db_client"] is db_client


@patch("obi_one.core.run_tasks.db_sdk.get_entity_asset_by_label")
@patch("obi_one.core.run_tasks.get_task_spec_for_task_type")
@patch("obi_one.core.run_tasks.deserialize_obi_object_from_json_data")
def test_run_task_type_downloads_config_deserializes_sets_entity_and_executes_task(
    mock_deserialize,
    mock_get_task_spec_for_task_type,
    mock_get_asset,
    db_client,
    mock_single_config,
):
    entity_type = MagicMock()
    mock_task_cls = MagicMock()
    mock_task_instance = MagicMock()
    mock_task_cls.return_value = mock_task_instance
    mock_get_task_spec_for_task_type.return_value = SimpleNamespace(
        asset_label=MagicMock(),
        task_cls=mock_task_cls,
        single_config_cls=MagicMock(),
    )
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
    mock_get_task_spec_for_task_type.assert_called_once_with(TaskType.circuit_extraction)
    mock_task_cls.assert_called_once_with(config=mock_single_config)
    mock_task_instance.execute.assert_called_once_with(
        db_client=db_client,
        entity_cache=True,
        execution_activity_id="act-1",
    )


@patch("obi_one.core.run_tasks.get_task_spec_for_task_type")
def test_run_task_type_without_asset_label_creates_default_config(
    mock_get_task_spec_for_task_type,
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
    mock_get_task_spec_for_task_type.return_value = SimpleNamespace(
        asset_label=None,
        single_config_cls=mock_config_cls,
        task_cls=mock_task_cls,
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

    # Should not download content (no asset)
    db_client.download_content.assert_not_called()

    # Should create config from single config class
    mock_config_cls.assert_called_once_with(scan_output_root="/out")
    mock_config_instance.set_single_entity.assert_called_once_with(
        db_client.get_entity.return_value
    )

    # Should execute the task
    mock_task_cls.assert_called_once_with(config=mock_config_instance)
    mock_task_instance.execute.assert_called_once_with(
        db_client=db_client,
        entity_cache=False,
        execution_activity_id="act-1",
    )


@patch.object(CircuitExtractionTask, "execute", return_value="done")
def test_run_task_for_single_config_executes_registered_task(mock_execute):
    config = CircuitExtractionSingleConfig.model_construct()

    result = test_module.run_task_for_single_config(config, db_client=MagicMock())

    assert result == "done"
    mock_execute.assert_called_once()


@patch("obi_one.core.run_tasks.get_task_spec_for_single_config")
def test_run_task_for_single_config_unknown_class_raises(mock_get_task_spec, mock_single_config):
    mock_get_task_spec.return_value = None

    with pytest.raises(KeyError, match="No task registered"):
        test_module.run_task_for_single_config(mock_single_config)

    mock_get_task_spec.assert_called_once_with(mock_single_config.__class__)


@patch("obi_one.core.run_tasks.get_task_spec_for_single_config")
def test_run_task_for_single_config_subclass_mismatch_raises(
    mock_get_task_spec, mock_single_config
):
    other_config_cls = type("OtherSingleConfig", (), {})
    mock_get_task_spec.return_value = SimpleNamespace(
        single_config_cls=other_config_cls,
        task_cls=MagicMock(),
    )

    with pytest.raises(KeyError, match="No task registered"):
        test_module.run_task_for_single_config(mock_single_config)


@patch("obi_one.core.run_tasks.run_task_for_single_config")
def test_run_task_for_single_configs_runs_each(mock_run_single, mock_single_config):
    configs = [mock_single_config, mock_single_config]
    mock_run_single.return_value = "ok"

    result = test_module.run_task_for_single_configs(configs, db_client=MagicMock())

    assert result == ["ok", "ok"]
    assert mock_run_single.call_count == 2


@patch("obi_one.core.run_tasks.run_task_for_single_configs")
def test_run_tasks_for_generated_scan_delegates(mock_run_configs):
    scan = MagicMock()
    scan.single_configs = [MagicMock()]
    db_client = MagicMock()

    test_module.run_tasks_for_generated_scan(scan, db_client=db_client, entity_cache=True)

    mock_run_configs.assert_called_once_with(
        scan.single_configs,
        db_client=db_client,
        entity_cache=True,
        execution_activity_id=None,
    )


@patch("obi_one.core.run_tasks.run_task_for_single_config")
@patch("obi_one.core.run_tasks.deserialize_obi_object_from_json_data")
def test_run_task_for_single_config_asset_deserializes_and_runs(
    mock_deserialize, mock_run_single, db_client, mock_single_config
):
    mock_deserialize.return_value = mock_single_config

    test_module.run_task_for_single_config_asset(
        entity_type=MagicMock(),
        entity_id="ent-1",
        config_asset_id="asset-1",
        scan_output_root="/out",
        db_client=db_client,
    )

    call_json_dict = mock_deserialize.call_args[0][0]
    assert call_json_dict["scan_output_root"] == "/out"
    assert call_json_dict["coordinate_output_root"] == Path("/out") / "0"
    mock_single_config.set_single_entity.assert_called_once()
    mock_run_single.assert_called_once()


@patch("obi_one.core.run_tasks.db_sdk.get_entity_asset_by_label")
@patch("obi_one.core.run_tasks.get_task_spec_for_task_type")
def test_run_task_type_raises_when_config_asset_has_no_id(
    mock_get_task_spec_for_task_type, mock_get_asset, db_client
):
    mock_get_task_spec_for_task_type.return_value = SimpleNamespace(
        asset_label=MagicMock(),
        task_cls=MagicMock(),
        single_config_cls=MagicMock(),
    )
    mock_get_asset.return_value = SimpleNamespace(id=None)

    with pytest.raises(ValueError, match="Config asset must have an id"):
        test_module.run_task_type(
            TaskType.circuit_extraction,
            entity_type=MagicMock(),
            entity_id="ent-1",
            scan_output_root="/out",
            db_client=db_client,
        )

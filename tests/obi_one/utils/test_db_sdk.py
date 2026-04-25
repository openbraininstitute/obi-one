import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import entitysdk
import httpx
import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.models import Asset, Entity, SimulationExecution
from entitysdk.types import AssetLabel, ContentType, ExecutorType, TaskActivityType

from obi_one.core.exception import OBIONEError
from obi_one.utils import db_sdk as test_module


@pytest.fixture
def mock_http_client():
    return Mock(spec=httpx.Client)


@pytest.fixture
def client():
    """Mock entitysdk Client with spec."""
    return entitysdk.Client(api_url="http://my-url", token_manager="my-token")  # noqa: S106


@pytest.fixture
def mock_entity():
    """Mock Entity object."""
    return MagicMock(spec=Entity, id=uuid4())


@pytest.fixture
def mock_entity_with_assets():
    """Mock config Entity for asset selection."""
    config = Mock(spec=Entity)
    config.id = uuid4()
    config.assets = [
        Mock(spec=Asset, label=AssetLabel.morphology),
        Mock(spec=Asset, label=AssetLabel.circuit_extraction_config),
    ]
    return config


def test_get_entity_asset_by_label(client, mock_entity_with_assets):
    """Test successful retrieval of config asset"""
    result = test_module.get_entity_asset_by_label(
        client=client,
        config=mock_entity_with_assets,
        asset_label=AssetLabel.morphology,
    )
    assert result.label == AssetLabel.morphology


def test_get_task_config_asset():
    client = Mock()
    config = Mock(spec=Entity)
    config.id = uuid4()
    expected_asset = Mock(spec=Asset, label=AssetLabel.task_config)
    client.select_assets.return_value.one.return_value = expected_asset

    result = test_module.get_task_config_asset(client=client, config=config)

    assert result is expected_asset
    client.select_assets.assert_called_once_with(
        entity=config,
        selection={"label": AssetLabel.task_config},
    )


def test_create_activity(client, mock_entity, httpx_mock):
    """Test successful activity creation."""
    activity_status = "pending"

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the request payload plus an id."""
        payload = json.loads(request.content)
        return httpx.Response(status_code=200, json=payload | {"id": str(uuid4())})

    httpx_mock.add_callback(
        handler,
        url="http://my-url/simulation-execution",
        method="POST",
    )

    result = test_module.create_activity(
        client=client,
        activity_type=SimulationExecution,
        activity_status=activity_status,
        used=[mock_entity],
    )
    assert result.status == activity_status


def test_create_generic_activity(client, mock_entity, httpx_mock):
    """Test successful activity creation."""
    activity_status = "pending"

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the request payload plus an id."""
        payload = json.loads(request.content)
        return httpx.Response(status_code=200, json=payload | {"id": str(uuid4())})

    httpx_mock.add_callback(
        handler,
        url="http://my-url/task-activity",
        method="POST",
    )

    result = test_module.create_generic_activity(
        client=client,
        activity_type=TaskActivityType.circuit_extraction__execution,
        activity_status=activity_status,
        used=[mock_entity],
    )
    assert result.status == activity_status


def test_update_activity_status(client, httpx_mock):
    """Test successful activity status update."""
    activity_id = uuid4()
    new_status = "running"

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the request payload plus an id."""
        payload = json.loads(request.content)
        return httpx.Response(
            status_code=200, json=payload | {"start_time": datetime.now(UTC).isoformat()}
        )

    httpx_mock.add_callback(
        handler,
        url=f"http://my-url/simulation-execution/{activity_id}",
        method="PATCH",
    )

    result = test_module.update_activity_status(
        client=client,
        activity_id=activity_id,
        activity_type=SimulationExecution,
        status=new_status,
    )

    assert result.status == new_status


def test_update_activity_executor(client, httpx_mock):
    """Test successful activity executor update."""
    activity_id = uuid4()
    execution_id = uuid4()
    executor = ExecutorType.single_node_job

    def handler(request: httpx.Request) -> httpx.Response:
        """Return the request payload plus an id."""
        payload = json.loads(request.content)
        return httpx.Response(
            status_code=200,
            json=payload | {"start_time": datetime.now(UTC).isoformat(), "status": "running"},
        )

    httpx_mock.add_callback(
        handler,
        url=f"http://my-url/simulation-execution/{activity_id}",
        method="PATCH",
    )

    result = test_module.update_activity_executor(
        client=client,
        activity_id=activity_id,
        activity_type=SimulationExecution,
        execution_id=execution_id,
        executor=executor,
    )

    assert result.executor == executor
    assert result.execution_id == execution_id


def test_get_activity_status(client, httpx_mock):
    """Test successful retrieval of activity status."""
    activity_id = uuid4()

    httpx_mock.add_response(
        url=f"http://my-url/simulation-execution/{activity_id}",
        method="GET",
        json={
            "start_time": datetime.now(UTC).isoformat(),
            "status": "done",
        },
    )

    result = test_module.get_activity_status(
        client=client,
        activity_id=activity_id,
        activity_type=SimulationExecution,
    )

    assert result == "done"


def test_get_entity_asset_by_label_raises():
    client = Mock()
    config = Mock(spec=Entity)
    config.id = uuid4()
    config.type = "task_config"
    config.assets = []
    client.select_assets.return_value.one.side_effect = EntitySDKError("missing")

    with pytest.raises(OBIONEError, match="Could not find asset with label"):
        test_module.get_entity_asset_by_label(
            client=client,
            config=config,
            asset_label=AssetLabel.morphology,
        )


def test_register_task_config_entity():
    client = Mock()
    registered = Mock()
    client.register_entity.return_value = registered

    result = test_module.register_task_config_entity(
        client=client,
        name="n",
        description="d",
        task_config_type="em_synapse_mapping__config",
        multiple_value_parameters_dictionary={"a": [1]},
        input_entities=[Mock(spec=Entity)],
    )

    assert result is registered
    client.register_entity.assert_called_once()


def test_upload_task_config_asset(tmp_path):
    client = Mock()
    entity = Mock(spec=Entity)
    entity.id = uuid4()
    file_path = tmp_path / "config.json"
    file_path.write_text("{}")
    uploaded_asset = Mock(spec=Asset)
    client.upload_file.return_value = uploaded_asset

    result = test_module.upload_task_config_asset(client=client, entity=entity, file_path=file_path)

    assert result is uploaded_asset
    client.upload_file.assert_called_once()


def test_register_task_config_with_asset(tmp_path):
    client = Mock()
    task_config_entity = Mock()
    asset = Mock(spec=Asset)
    config_path = tmp_path / "task_config.json"
    config_path.write_text("{}")

    with (
        pytest.MonkeyPatch.context() as mp,
    ):
        mp.setattr(
            test_module, "register_task_config_entity", Mock(return_value=task_config_entity)
        )
        mp.setattr(test_module, "upload_task_config_asset", Mock(return_value=asset))

        result_entity, result_asset = test_module.register_task_config_with_asset(
            client=client,
            name="name",
            description="desc",
            task_config_type="my_type",
            multiple_value_parameters_dictionary={"p": [1, 2]},
            input_entities=[uuid4()],
            task_config_file_path=config_path,
        )

    assert result_entity is task_config_entity
    assert result_asset is asset


def test_update_execution_activity_with_generated():
    client = Mock()
    updated = Mock()
    client.update_entity.return_value = updated
    execution_activity_id = uuid4()

    result = test_module.update_execution_activity_with_generated(
        client=client,
        execution_activity_id=execution_activity_id,
        generated_ids=["a", "b"],
    )

    assert result is updated
    client.update_entity.assert_called_once()


def test_get_execution_activity():
    client = Mock()
    execution_activity = Mock()
    client.get_entity.return_value = execution_activity
    execution_activity_id = uuid4()

    result = test_module.get_execution_activity(
        client=client,
        execution_activity_id=execution_activity_id,
    )

    assert result is execution_activity
    client.get_entity.assert_called_once()


def test_add_circuit_folder_asset_missing_folder(tmp_path):
    client = Mock()
    with pytest.raises(FileNotFoundError, match="Circuit folder does not exist"):
        test_module.add_circuit_folder_asset(
            client=client,
            circuit_path=tmp_path / "missing" / "circuit_config.json",
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_circuit_folder_asset_missing_circuit_config(tmp_path):
    circuit_folder = tmp_path / "circuit"
    circuit_folder.mkdir()
    (circuit_folder / "node_sets.json").write_text("{}")
    client = Mock()

    with pytest.raises(FileNotFoundError, match="Circuit config file not found"):
        test_module.add_circuit_folder_asset(
            client=client,
            circuit_path=circuit_folder / "circuit_config.json",
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_circuit_folder_asset_missing_node_sets(tmp_path):
    circuit_folder = tmp_path / "circuit"
    circuit_folder.mkdir()
    (circuit_folder / "circuit_config.json").write_text("{}")
    client = Mock()

    with pytest.raises(FileNotFoundError, match="Node sets file not found"):
        test_module.add_circuit_folder_asset(
            client=client,
            circuit_path=circuit_folder / "circuit_config.json",
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_circuit_folder_asset_success(tmp_path):
    circuit_folder = tmp_path / "circuit"
    circuit_folder.mkdir()
    (circuit_folder / "circuit_config.json").write_text("{}")
    (circuit_folder / "node_sets.json").write_text("{}")
    (circuit_folder / "nodes.h5").write_text("x")
    client = Mock()
    directory_asset = SimpleNamespace(id=uuid4())
    client.upload_directory.return_value = directory_asset

    result = test_module.add_circuit_folder_asset(
        client=client,
        circuit_path=circuit_folder / "circuit_config.json",
        registered_circuit=Mock(id=uuid4()),
    )

    assert result is directory_asset
    client.upload_directory.assert_called_once()


def test_add_compressed_circuit_asset_missing_file(tmp_path):
    client = Mock()
    with pytest.raises(FileNotFoundError, match="does not exist"):
        test_module.add_compressed_circuit_asset(
            client=client,
            compressed_file=tmp_path / "missing.tar.gz",
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_compressed_circuit_asset_success(tmp_path):
    compressed_file = tmp_path / "circuit.tar.gz"
    compressed_file.write_bytes(b"abc")
    client = Mock()
    compressed_asset = SimpleNamespace(id=uuid4())
    client.upload_file.return_value = compressed_asset

    result = test_module.add_compressed_circuit_asset(
        client=client,
        compressed_file=compressed_file,
        registered_circuit=Mock(id=uuid4()),
    )

    assert result is compressed_asset
    client.upload_file.assert_called_once()


def test_add_connectivity_matrix_asset_missing_dir(tmp_path):
    client = Mock()
    with pytest.raises(FileNotFoundError, match="does not exist"):
        test_module.add_connectivity_matrix_asset(
            client=client,
            matrix_dir=tmp_path / "missing",
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_connectivity_matrix_asset_success(tmp_path):
    matrix_dir = tmp_path / "matrices"
    matrix_dir.mkdir()
    (matrix_dir / "m1.npy").write_text("x")
    client = Mock()
    matrix_asset = SimpleNamespace(id=uuid4())
    client.upload_directory.return_value = matrix_asset

    result = test_module.add_connectivity_matrix_asset(
        client=client,
        matrix_dir=matrix_dir,
        registered_circuit=Mock(id=uuid4()),
    )

    assert result is matrix_asset
    client.upload_directory.assert_called_once()


def test_add_image_assets_missing_dir(tmp_path):
    client = Mock()
    with pytest.raises(FileNotFoundError, match="does not exist"):
        test_module.add_image_assets(
            client=client,
            plot_dir=tmp_path / "missing",
            plot_files=[],
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_image_assets_missing_file(tmp_path):
    plot_dir = tmp_path / "plots"
    plot_dir.mkdir()
    client = Mock()
    with pytest.raises(FileNotFoundError, match="does not exist"):
        test_module.add_image_assets(
            client=client,
            plot_dir=plot_dir,
            plot_files=["node_stats.png"],
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_image_assets_skip_unknown_plot(tmp_path):
    plot_dir = tmp_path / "plots"
    plot_dir.mkdir()
    (plot_dir / "unknown.png").write_bytes(b"x")
    client = Mock()

    assets = test_module.add_image_assets(
        client=client,
        plot_dir=plot_dir,
        plot_files=["unknown.png"],
        registered_circuit=Mock(id=uuid4()),
    )

    assert assets == []
    client.upload_file.assert_not_called()


def test_add_image_assets_format_mismatch(tmp_path):
    plot_dir = tmp_path / "plots"
    plot_dir.mkdir()
    (plot_dir / "simulation_designer_image.jpg").write_bytes(b"x")
    client = Mock()

    with pytest.raises(ValueError, match="File format mismatch"):
        test_module.add_image_assets(
            client=client,
            plot_dir=plot_dir,
            plot_files=["simulation_designer_image.jpg"],
            registered_circuit=Mock(id=uuid4()),
        )


def test_add_image_assets_success_webp_and_png(tmp_path):
    plot_dir = tmp_path / "plots"
    plot_dir.mkdir()
    node_stats_png = plot_dir / "node_stats.png"
    node_stats_png.write_bytes(b"x")
    sim_png = plot_dir / "simulation_designer_image.png"
    sim_png.write_bytes(b"y")

    client = Mock()
    uploaded_a = SimpleNamespace(id=uuid4())
    uploaded_b = SimpleNamespace(id=uuid4())
    client.upload_file.side_effect = [uploaded_a, uploaded_b]

    converted = plot_dir / "node_stats.webp"
    converted.write_bytes(b"z")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(test_module, "convert_image_to_webp", Mock(return_value=Path(converted)))
        assets = test_module.add_image_assets(
            client=client,
            plot_dir=plot_dir,
            plot_files=["node_stats.png", "simulation_designer_image.png"],
            registered_circuit=Mock(id=uuid4()),
        )

    assert assets == [uploaded_a, uploaded_b]
    assert client.upload_file.call_count == 2


def test_select_json_asset_content(client, httpx_mock):
    entity_id = uuid4()
    asset_1_id = uuid4()
    asset_2_id = uuid4()

    entity = Entity(
        id=entity_id,
        name="foo",
        assets=[
            Asset(
                id=asset_1_id,
                path="config.json",
                full_path="/config.json",
                content_type=ContentType.application_json,
                size=0,
                storage_type="aws_s3_internal",
                label=AssetLabel.sonata_simulation_config,
                is_directory=False,
            ),
            Asset(
                id=asset_2_id,
                path="foo.swc",
                full_path="/foo.swc",
                content_type=ContentType.application_swc,
                size=0,
                storage_type="aws_s3_internal",
                label=AssetLabel.morphology,
                is_directory=False,
            ),
        ],
    )
    content = {"foo": "bar", "zee": "roo"}
    httpx_mock.add_response(
        url=f"{client.api_url}/entity/{entity_id}/assets/{asset_1_id}/download",
        content=json.dumps(content),
        is_reusable=True,
    )
    res = test_module.select_json_asset_content(
        client=client,
        entity=entity,
        selection={"label": AssetLabel.sonata_simulation_config},
    )
    assert res == content

    httpx_mock.add_response(
        url=f"{client.api_url}/entity/{entity_id}",
        json=entity.model_dump(mode="json"),
    )

    res = test_module.select_json_asset_content(
        client=client,
        entity_id=entity.id,
        entity_type=type(entity),
        selection={"label": AssetLabel.sonata_simulation_config},
    )
    assert res == content

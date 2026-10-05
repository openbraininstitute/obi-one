import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import entitysdk
import httpx
import pytest
from entitysdk.common import ProjectContext
from entitysdk.exception import EntitySDKError
from entitysdk.models import Asset, Entity, SimulationExecution
from entitysdk.types import AssetLabel, ContentType, ExecutorType, TaskActivityType

from obi_one.core.exception import OBIONEError
from obi_one.db_sdk import db_sdk as test_module
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit

from tests.utils import CIRCUIT_DIR, PROJECT_ID, VIRTUAL_LAB_ID


@pytest.fixture
def mock_http_client():
    return Mock(spec=httpx.Client)


@pytest.fixture
def client():
    """Mock entitysdk Client with spec."""
    return entitysdk.Client(
        api_url="http://my-url",
        token_manager="my-token",  # ruff: ignore[hardcoded-password-func-arg]
        project_context=ProjectContext(virtual_lab_id=VIRTUAL_LAB_ID, project_id=PROJECT_ID),
    )


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


def test_get_identifiable():
    identifiable_id = uuid4()
    resource = Mock(id=identifiable_id)
    client = Mock()
    client.get_entity.return_value = resource

    result = test_module.get_identifiable(
        client=client,
        identifiable_id=identifiable_id,
        identifiable_type=SimulationExecution,
    )

    assert result is resource
    client.get_entity.assert_called_once_with(
        entity_id=identifiable_id,
        entity_type=SimulationExecution,
    )


def test_get_identifiable_raises_when_id_missing():
    client = Mock()
    client.get_entity.return_value = Mock(id=None)

    with pytest.raises(OBIONEError, match="has no ID"):
        test_module.get_identifiable(
            client=client,
            identifiable_id=uuid4(),
            identifiable_type=SimulationExecution,
        )


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


def test_get_task_config_asset_content():
    client = Mock()
    config = Mock(spec=Entity)
    config.id = uuid4()
    expected_content = {"type": "CircuitSimplificationSingleConfig"}

    with patch.object(
        test_module,
        "select_json_asset_content",
        return_value=expected_content,
    ) as mock_select_json_asset_content:
        result = test_module.get_task_config_asset_content(client=client, config=config)

    assert result == expected_content
    mock_select_json_asset_content.assert_called_once_with(
        client=client,
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


def test_finalize_activity(client, httpx_mock):
    """Test successful activity finalization."""
    activity_id = uuid4()
    end_time = datetime.now(UTC)
    finalized_status = "done"

    def handler(request: httpx.Request) -> httpx.Response:
        """Return patched payload plus required start time."""
        payload = json.loads(request.content)
        return httpx.Response(
            status_code=200,
            json=payload | {"start_time": datetime.now(UTC).isoformat()},
        )

    httpx_mock.add_callback(
        handler,
        url=f"http://my-url/simulation-execution/{activity_id}",
        method="PATCH",
    )

    result = test_module.finalize_activity(
        client=client,
        activity_id=activity_id,
        activity_type=SimulationExecution,
        status=finalized_status,
        end_time=end_time,
    )

    assert result.status == finalized_status
    assert result.end_time == end_time


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


def test_resolve_circuit_local_instance():
    circuit_path = CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"
    circuit = Circuit(name="local", path=str(circuit_path))

    resolved, entity = test_module.resolve_circuit(
        circuit,
        db_client=Mock(),
        entity_cache=False,
        cache_root=Path("/cache"),
        temp_dir=Path("/temp"),
    )

    assert resolved is circuit
    assert entity is None


def test_resolve_circuit_from_id_without_cache(tmp_path):
    db_client = Mock()
    circuit_from_id = CircuitFromID(id_str="circuit-1")
    staged_circuit = Mock(spec=Circuit)
    circuit_entity = Mock()

    with (
        patch.object(CircuitFromID, "stage_circuit", return_value=staged_circuit) as mock_stage,
        patch.object(CircuitFromID, "entity", return_value=circuit_entity),
    ):
        resolved, entity = test_module.resolve_circuit(
            circuit_from_id,
            db_client=db_client,
            entity_cache=False,
            cache_root=tmp_path / "cache",
            temp_dir=tmp_path / "temp",
        )

    assert resolved is staged_circuit
    assert entity is circuit_entity
    mock_stage.assert_called_once_with(
        db_client=db_client,
        dest_dir=tmp_path / "temp" / "sonata_circuit",
        entity_cache=False,
    )


def test_resolve_circuit_from_id_with_cache(tmp_path):
    db_client = Mock()
    circuit_from_id = CircuitFromID(id_str="circuit-1")
    staged_circuit = Mock(spec=Circuit)
    circuit_entity = Mock()

    with (
        patch.object(CircuitFromID, "stage_circuit", return_value=staged_circuit) as mock_stage,
        patch.object(CircuitFromID, "entity", return_value=circuit_entity),
    ):
        resolved, entity = test_module.resolve_circuit(
            circuit_from_id,
            db_client=db_client,
            entity_cache=True,
            cache_root=tmp_path / "cache",
            temp_dir=tmp_path / "temp",
        )

    assert resolved is staged_circuit
    assert entity is circuit_entity
    mock_stage.assert_called_once_with(
        db_client=db_client,
        dest_dir=tmp_path / "cache" / "entity_cache" / "sonata_circuit" / "circuit-1",
        entity_cache=True,
    )


def test_resolve_circuit_unsupported_type():
    with pytest.raises(OBIONEError, match="Unsupported circuit type"):
        test_module.resolve_circuit(
            "not-a-circuit",
            db_client=Mock(),
            entity_cache=False,
            cache_root=Path("/cache"),
            temp_dir=Path("/temp"),
        )


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

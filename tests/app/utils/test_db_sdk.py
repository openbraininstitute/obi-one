import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import entitysdk
import httpx
import pytest
from entitysdk.models import Asset, Entity, SimulationExecution
from entitysdk.types import AssetLabel, ExecutorType

from app.utils import db_sdk as test_module


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


def test_get_config_asset(client, mock_entity_with_assets):
    """Test successful retrieval of config asset"""
    result = test_module.get_config_asset(
        client=client,
        config=mock_entity_with_assets,
        asset_label=AssetLabel.morphology,
    )
    assert result.label == AssetLabel.morphology


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

from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import quote, unquote
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.file import _create_temp_dir
from app.endpoints.circuit_visualization import router

ROUTER_MODULE = "app.endpoints.circuit_visualization"


@pytest.fixture
def mock_db_client():
    return MagicMock()


@pytest.fixture
def client(tmp_path, mock_db_client):
    app = FastAPI()
    app.include_router(router)

    def mock_user_verified():
        return True

    app.dependency_overrides[user_verified] = mock_user_verified
    app.dependency_overrides[get_client] = lambda: mock_db_client

    app.dependency_overrides[_create_temp_dir] = lambda: tmp_path
    return TestClient(app)


@patch(f"{ROUTER_MODULE}.get_nodes")
@patch(f"{ROUTER_MODULE}.download_circuit_config")
@patch(f"{ROUTER_MODULE}.circuit_asset_id")
def test_circuit_nodes(
    mock_circuit_asset_id,
    mock_download_circuit_config,
    mock_get_nodes,
    client,
    mock_db_client,
):
    circuit_id = uuid4()

    asset_id = uuid4()

    mock_nodes = [
        {
            "morphology_path": "test_path",
            "position": [0.1, 0.2, 0.3],
            "orientation": [0.1, 0.2, 0.3, 0.4],
            "soma_radius": 0.5,
        }
    ]

    mock_circuit_asset_id.return_value = asset_id
    mock_download_circuit_config.return_value = {"config": "dummy"}
    mock_get_nodes.return_value = mock_nodes

    response = client.get(f"/circuit/viz/{str(circuit_id)}/nodes")  # noqa: RUF010

    assert response.status_code == 200
    assert response.json() == mock_nodes

    mock_circuit_asset_id.assert_called_once_with(mock_db_client, circuit_id)
    mock_download_circuit_config.assert_called_once()
    mock_get_nodes.assert_called_once()


@patch(f"{ROUTER_MODULE}.get_morphology")
@patch(f"{ROUTER_MODULE}.circuit_asset_id")
def test_circuit_morphology(
    mock_circuit_asset_id, mock_get_morphology, client, mock_db_client, tmp_path
):
    circuit_id = uuid4()
    asset_id = uuid4()
    morphology_path = quote("dir/mock_path", safe="")

    mock_circuit_asset_id.return_value = asset_id
    mock_get_morphology.return_value = {}
    response = client.get(f"/circuit/viz/{str(circuit_id)}/morphologies/{morphology_path}")  # noqa: RUF010

    assert response.status_code == 200
    assert response.json() == {}

    mock_circuit_asset_id.assert_called_once_with(mock_db_client, circuit_id)
    mock_get_morphology.assert_called_once_with(
        tmp_path, mock_db_client, circuit_id, asset_id, Path(f"{unquote(morphology_path)}.swc")
    )

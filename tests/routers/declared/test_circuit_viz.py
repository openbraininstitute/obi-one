from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from urllib.parse import quote, unquote
from uuid import uuid4
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.file import _create_temp_dir
from app.endpoints.circuit_visualization import router
from app.services.circuit_visualization import circuit_asset_id
from entitysdk.models import Circuit, Asset
from entitysdk.models.asset import AssetLabel, StorageType, ContentType
from entitysdk.models.circuit import CircuitScale, CircuitBuildCategory
from entitysdk.exception import EntitySDKError
from app.errors import ApiErrorCode
from uuid import UUID


from fastapi import HTTPException
from http import HTTPStatus

ROUTER_MODULE = "app.endpoints.circuit_visualization"


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def client(tmp_path, mock_client):
    app = FastAPI()
    app.include_router(router)

    def mock_user_verified():
        return True

    app.dependency_overrides[user_verified] = mock_user_verified
    app.dependency_overrides[get_client] = lambda: mock_client

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
    mock_client,
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

    mock_circuit_asset_id.assert_called_once_with(mock_client, circuit_id)
    mock_download_circuit_config.assert_called_once()
    mock_get_nodes.assert_called_once()


@patch(f"{ROUTER_MODULE}.get_morphology")
@patch(f"{ROUTER_MODULE}.circuit_asset_id")
def test_circuit_morphology(
    mock_circuit_asset_id, mock_get_morphology, client, mock_client, tmp_path
):
    circuit_id = uuid4()
    asset_id = uuid4()
    morphology_path = quote("dir/mock_path", safe="")

    mock_circuit_asset_id.return_value = asset_id
    mock_get_morphology.return_value = {}
    response = client.get(f"/circuit/viz/{str(circuit_id)}/morphologies/{morphology_path}")  # noqa: RUF010

    assert response.status_code == 200
    assert response.json() == {}

    mock_circuit_asset_id.assert_called_once_with(mock_client, circuit_id)
    mock_get_morphology.assert_called_once_with(
        tmp_path, mock_client, circuit_id, asset_id, Path(f"{unquote(morphology_path)}.swc")
    )


@pytest.fixture
def test_asset_dict():
    return {
        "id": uuid4(),
        "path": "relative/path/to/circuit",
        "full_path": "s3://bucket/relative/path/to/circuit",
        "storage_type": StorageType.aws_s3_open,
        "is_directory": True,
        "content_type": ContentType.application_vnd_directory,
        "size": 1024,
        "label": AssetLabel.sonata_circuit,
    }


@pytest.fixture
def test_circuit_dict():
    return {
        "id": uuid4(),
        "number_neurons": 10,
        "number_synapses": 100,
        "number_connections": 100,
        "build_category": CircuitBuildCategory.em_reconstruction,
    }


def test_circuit_asset_id_success(mock_client, test_circuit_dict, test_asset_dict):
    test_circuit = Circuit(
        **test_circuit_dict, assets=[Asset(**test_asset_dict)], scale=CircuitScale.small
    )

    expected_asset_id = test_circuit.assets[0].id

    mock_client.get_entity.return_value = test_circuit

    result = circuit_asset_id(mock_client, cast("UUID", test_circuit.id))

    assert result == expected_asset_id
    mock_client.get_entity.assert_called_once_with(entity_id=test_circuit.id, entity_type=Circuit)


def test_circuit_asset_id_sdk_error(mock_client):
    circuit_id = uuid4()
    mock_client.get_entity.side_effect = EntitySDKError("Fetch failed")

    with pytest.raises(HTTPException) as exc_info:
        circuit_asset_id(mock_client, circuit_id)

    assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST

    assert exc_info.value.detail["code"] == ApiErrorCode.INVALID_REQUEST
    assert exc_info.value.detail["detail"] == "Couldn't fetch the circuit"


def test_circuit_asset_id_invalid_scale(mock_client, test_circuit_dict, test_asset_dict):
    test_circuit = Circuit(
        **test_circuit_dict, assets=[Asset(**test_asset_dict)], scale=CircuitScale.microcircuit
    )

    mock_client.get_entity.return_value = test_circuit

    with pytest.raises(HTTPException) as exc_info:
        circuit_asset_id(mock_client, cast("UUID", test_circuit.id))

    assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
    assert exc_info.value.detail["detail"] == "Circuit's scale should be 'small' or 'pair'"


def test_circuit_asset_id_missing_asset(mock_client, test_circuit_dict):
    test_circuit = Circuit(**test_circuit_dict, assets=[], scale=CircuitScale.small)

    mock_client.get_entity.return_value = test_circuit

    with pytest.raises(HTTPException) as exc_info:
        circuit_asset_id(mock_client, cast("UUID", test_circuit.id))

    assert exc_info.value.status_code == HTTPStatus.BAD_REQUEST
    assert exc_info.value.detail["detail"] == "Circuit is missing a sonata_circuit asset"

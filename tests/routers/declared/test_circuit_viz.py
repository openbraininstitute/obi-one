from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch
from urllib.parse import quote, unquote
from uuid import UUID, uuid4

import libsonata
import pytest
from entitysdk.models import Asset, Circuit
from entitysdk.models.asset import AssetLabel, ContentType, StorageType
from entitysdk.models.circuit import CircuitBuildCategory, CircuitScale
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.dependencies.file import _create_temp_dir
from app.endpoints.circuit_visualization import router
from app.schemas.visualization import NeuronSectionInfo, Node
from app.services.circuit_visualization import (
    circuit_asset_id,
    download_circuit_config,
    get_morphology,
    get_nodes,
)

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
            "morphology_file": "test_file",
            "morphology_name": "test_name",
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


def test_circuit_asset_id(mock_client, test_circuit_dict, test_asset_dict):
    test_circuit = Circuit(
        **test_circuit_dict, assets=[Asset(**test_asset_dict)], scale=CircuitScale.small
    )

    expected_asset_id = test_circuit.assets[0].id

    mock_client.get_entity.return_value = test_circuit

    result = circuit_asset_id(mock_client, cast("UUID", test_circuit.id))

    assert result == expected_asset_id
    mock_client.get_entity.assert_called_once_with(entity_id=test_circuit.id, entity_type=Circuit)


@pytest.fixture
def test_circuit_dir():
    # return Path("./examples/data/tiny_circuits/N_10__top_nodes_dim6").resolve()
    return Path("./examples/data/tiny_circuits/nbS1-O1-E2Sst-maxNsyn-HEX0-L5").resolve()


@pytest.fixture
def test_sonata_config(test_circuit_dir):
    return libsonata.CircuitConfig(
        (test_circuit_dir / "circuit_config.json").read_text(), str(test_circuit_dir)
    )


def test_download_circuit_config(mock_client, test_circuit_dir):
    circuit_id = uuid4()
    asset_id = uuid4()

    result = download_circuit_config(mock_client, circuit_id, asset_id, test_circuit_dir)

    mock_client.download_file.assert_called_once_with(
        entity_id=circuit_id,
        entity_type=Circuit,
        asset_id=asset_id,
        output_path=test_circuit_dir / "circuit_config.json",
        asset_path=Path("circuit_config.json"),
    )

    assert isinstance(result, libsonata.CircuitConfig)


def test_get_nodes(test_sonata_config, mock_client, test_circuit_dir):
    test_nodes = [
        Node(
            morphology_file="morphologies/swc/dend-rp090908_c2_axon-vd110623_idA.swc",
            morphology_name="dend-rp090908_c2_axon-vd110623_idA",
            position=(3927.1862191305954, -1398.4124233327566, -2409.039000858357),
            orientation=(
                0.6971569742455114,
                0.5621838947816346,
                0.2816537095884868,
                0.3443727770658415,
            ),
            soma_radius=7.279230117797852,
        ),
        Node(
            morphology_file="morphologies/swc/rp110127_L5-2_idD_-_Clone_1.swc",
            morphology_name="rp110127_L5-2_idD_-_Clone_1",
            position=(3821.770720831846, -1368.8353733057893, -2569.5086101559486),
            orientation=(
                0.6809097129262709,
                0.5799801735168897,
                0.31893356942594736,
                0.3134746233161566,
            ),
            soma_radius=4.823882102966309,
        ),
    ]

    nodes = get_nodes(
        test_sonata_config,
        test_circuit_dir,
        mock_client,
        circuit_id=uuid4(),
        asset_id=uuid4(),
    )

    assert nodes == test_nodes


def test_get_morphology(mock_client, test_circuit_dir):
    morphology = get_morphology(
        test_circuit_dir,
        mock_client,
        uuid4(),
        uuid4(),
        Path("morphologies/swc/dend-rp090908_c2_axon-vd110623_idA" + ".swc"),
    )

    assert all(NeuronSectionInfo.model_validate(section) for section in morphology.values())

    axon_0 = morphology["axon[0]"]

    assert axon_0.nseg == 80
    assert axon_0.distance_from_soma == 0.0
    assert axon_0.sec_length == 126.4417724609375
    assert len(axon_0.xstart) == 80
    assert len(axon_0.xend) == 80

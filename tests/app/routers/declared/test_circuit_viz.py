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
from app.schemas.circuit_visualization import Section, Node
from app.services.circuit_visualization import (
    circuit_asset_id,
    download_circuit_config,
    get_morphology,
    get_morphology_data,
    get_nodes,
    resolve_morph_path,
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
@patch(f"{ROUTER_MODULE}.get_morphology_data")
@patch(f"{ROUTER_MODULE}.circuit_asset_id")
def test_circuit_morphology(
    mock_circuit_asset_id,
    mock_get_morphology_data,
    mock_get_morphology,
    client,
    mock_client,
    tmp_path,
):
    circuit_id = uuid4()
    asset_id = uuid4()
    morphology_path = quote("dir/mock_path.swc", safe="")
    name = "name"

    mock_circuit_asset_id.return_value = asset_id
    mock_get_morphology_data.return_value = []
    response = client.get(f"/circuit/viz/{circuit_id!s}/morphologies/{morphology_path}?name={name}")

    assert response.status_code == 200
    assert response.json() == []

    mock_circuit_asset_id.assert_called_once_with(mock_client, circuit_id)
    mock_get_morphology.assert_called_once_with(
        tmp_path,
        mock_client,
        circuit_id,
        asset_id,
        Path(f"{unquote(morphology_path)}"),
        name,
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
    mock_client.select_assets.return_value.one.return_value = test_circuit.assets[0]

    result = circuit_asset_id(mock_client, cast("UUID", test_circuit.id))

    assert result == expected_asset_id
    mock_client.get_entity.assert_called_once_with(entity_id=test_circuit.id, entity_type=Circuit)


@pytest.fixture
def test_circuit_dir():
    return Path("./examples/data/tiny_circuits/nbS1-O1-E2Sst-maxNsyn-HEX0-L5").resolve()


@pytest.fixture
def test_circuit_dir_alternate():
    return Path("./examples/data/tiny_circuits/N_10__top_nodes_dim6").resolve()


@pytest.fixture
def test_sonata_config(test_circuit_dir):
    return libsonata.CircuitConfig(
        (test_circuit_dir / "circuit_config.json").read_text(), str(test_circuit_dir)
    )


@pytest.fixture
def test_sonata_config_alternate(test_circuit_dir_alternate):
    return libsonata.CircuitConfig(
        (test_circuit_dir_alternate / "circuit_config.json").read_text(),
        str(test_circuit_dir_alternate),
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


def test_get_nodes_alternate(test_sonata_config_alternate, mock_client, test_circuit_dir_alternate):
    test_nodes = [
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="mtC181200C_idA_-_Scale_x1.000_y0.975_z1.000_-_Clone_0",
            position=(4426.676667727606, -1365.7203027217056, -1999.5555466483297),
            orientation=(
                0.5088851188368478,
                0.6512700087505278,
                0.5606842175110329,
                0.05016492562075268,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-mtC090401A_idB_axon-rp101228_L5-1_idA_-_Scale_x1.000_y1.025_z1.000",
            position=(3704.5844822609142, -1105.6184845061598, -2859.4254479996994),
            orientation=(
                0.43894370320376735,
                0.6528279568750848,
                0.6162888771434368,
                -0.03649800062123188,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-vd110330_idA_axon-tkb051205a4_ch3_cl_b_yw_60x_1_-_Scale_x1.000_y1.025_z1.000_-_Clone_1",
            position=(3592.5738932426484, -1084.0571344719174, -2963.7682802129993),
            orientation=(
                0.5453807827684773,
                -0.06941405345372872,
                -0.5252529464233355,
                0.6495004489941254,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-tkb060118b1_ch1_cc1_b_yw_60x_1_axon-rp110127_L5-3_idC_-_Scale_x1.000_y1.050_z1.000_-_Clone_1",
            position=(3627.3627856735347, -1087.1811025554398, -2897.810749201675),
            orientation=(
                0.5340070226377953,
                0.6482925192961682,
                0.5368122164342657,
                0.07991216105872467,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-Fluo18_lower_axon-rp110127_L5-3_idC_-_Scale_x1.000_y0.975_z1.000_-_Clone_0",
            position=(3537.776870743046, -1029.4458799141767, -2890.7837929060715),
            orientation=(
                0.31411801457818556,
                -0.31968204150274276,
                -0.6904054402710065,
                0.56786758430315,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-Fluo18_lower_axon-rp110127_L5-3_idC",
            position=(3592.6762765323256, -1025.0781011626223, -2898.148158944562),
            orientation=(
                0.6868891274225365,
                0.13568614438905097,
                -0.32009903295331554,
                0.6382078078117599,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-rat_20140925_RH2_cell2_axon-rp110125_L5-2_idF_-_Clone_4",
            position=(3639.4116185895655, -1055.0788533427767, -2834.3996988783433),
            orientation=(
                0.7517287337945563,
                0.323507268816347,
                -0.0958330582657927,
                0.5666241988779213,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-Fluo58_right_axon-rp110125_L5-2_idF_-_Clone_3",
            position=(3624.2011280185725, -1018.365265296854, -2890.523731834551),
            orientation=(
                0.6743863023409975,
                0.10624927962170909,
                -0.3583901187021639,
                0.6367658349906609,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="dend-tkb060523a2_ch5_cc2_n_nb_60x_1_axon-rp110125_L5-2_idF_-_Scale_x1.000_y1.050_z1.000_-_Clone_0",
            position=(3547.9258902260062, -1083.9810048266381, -2933.0711491645975),
            orientation=(
                0.6223943449583735,
                0.02224562016431142,
                -0.4287869416570199,
                0.6544250685997304,
            ),
            soma_radius=0.0,
        ),
        Node(
            morphology_file="morphologies/merged-morphologies.h5",
            morphology_name="rp110125_L5-2_idF_-_Scale_x1.000_y1.025_z1.000",
            position=(3663.108873689509, -1035.5517517738954, -2810.0420159102864),
            orientation=(
                0.6303434351321736,
                0.6158241138719361,
                0.4206509456244123,
                0.21559359105711814,
            ),
            soma_radius=0.0,
        ),
    ]

    nodes = get_nodes(
        test_sonata_config_alternate,
        test_circuit_dir_alternate,
        mock_client,
        circuit_id=uuid4(),
        asset_id=uuid4(),
    )

    assert nodes == test_nodes


def test_get_morphology(mock_client, test_circuit_dir):
    morph_raw = get_morphology(
        test_circuit_dir,
        mock_client,
        uuid4(),
        uuid4(),
        Path("morphologies/swc/dend-rp090908_c2_axon-vd110623_idA.swc"),
        None,
    )

    morphology_sections = get_morphology_data(morph_raw)
    sections = [Section.model_validate(section) for section in morphology_sections]
    assert (sections[0]).id == "soma"


def test_get_morphology_alternate(mock_client, test_circuit_dir_alternate):
    morph_raw = get_morphology(
        test_circuit_dir_alternate,
        mock_client,
        uuid4(),
        uuid4(),
        Path("morphologies/merged-morphologies.h5"),
        "rp110125_L5-2_idF_-_Scale_x1.000_y1.025_z1.000",
    )

    morphology_sections = get_morphology_data(morph_raw)

    sections = [Section.model_validate(section) for section in morphology_sections]

    assert (sections[0]).id == "soma"


def test_morphology_dir_fallback():
    config_path = Path("./examples/data/circuit_configs/circuit_config.json").resolve()
    config = libsonata.CircuitConfig(config_path.read_text(), "./examples/data/circuit_configs")
    path = resolve_morph_path("S1nonbarrel_neurons", config)
    assert path.path == Path("./examples/data/circuit_configs/test_dir").absolute()

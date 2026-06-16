"""Tests for obi_one.utils.circuit_customization.download."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from obi_one.utils.circuit_customization.download import (
    download_circuit_config,
    download_edge_populations,
    download_electrical_models,
    download_id_mapping,
    download_mechanisms,
    download_node_populations,
    download_node_sets,
    fetch_directory,
    fetch_file,
    get_sonata_asset,
)

CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")


@pytest.fixture
def circuit_id():
    return str(uuid4())


@pytest.fixture
def asset_id():
    return uuid4()


@pytest.fixture
def mock_asset(asset_id):
    asset = Mock()
    asset.id = asset_id
    asset.is_directory = True
    asset.label = Mock()
    asset.label.value = "sonata_circuit"
    return asset


@pytest.fixture
def mock_circuit_entity(mock_asset):
    entity = Mock()
    entity.assets = [mock_asset]
    return entity


@pytest.fixture
def mock_client(mock_circuit_entity):
    client = MagicMock()
    client.get_entity.return_value = mock_circuit_entity
    return client


def _make_fetch_file_side_effect(circuit_dir: Path):
    """Create a fetch_file side effect that copies from a local circuit directory."""

    def _fetch_file(*, entity_id, entity_type, asset_id, output_path, asset_path, strategy):  # noqa: ARG001
        src = circuit_dir / str(asset_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, output_path)
        else:
            output_path.touch()

    return _fetch_file


def _make_file_list(circuit_dir: Path):
    """Create a DetailedFileList mock from a local circuit directory."""
    file_list = Mock()
    files = {}
    for path in circuit_dir.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            rel = path.relative_to(circuit_dir)
            files[rel] = Mock()
    file_list.files = files
    return file_list


# --- _get_sonata_asset ---


def test_get_sonata_asset_success(mock_client, circuit_id, mock_circuit_entity, mock_asset):
    circuit, asset = get_sonata_asset(mock_client, circuit_id)
    assert circuit is mock_circuit_entity
    assert asset is mock_asset


def test_get_sonata_asset_no_asset(mock_client, circuit_id, mock_circuit_entity):
    mock_circuit_entity.assets = []
    with pytest.raises(ValueError, match="must have exactly one"):
        get_sonata_asset(mock_client, circuit_id)


def test_get_sonata_asset_multiple_assets(mock_client, circuit_id, mock_circuit_entity, mock_asset):
    mock_circuit_entity.assets = [mock_asset, mock_asset]
    with pytest.raises(ValueError, match="must have exactly one"):
        get_sonata_asset(mock_client, circuit_id)


# --- download_circuit_config ---


def test_download_circuit_config(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = download_circuit_config(circuit_id, mock_client, tmp_path)

    assert result == tmp_path / "circuit_config.json"
    assert result.exists()
    mock_client.fetch_file.assert_called_once()


# --- download_node_sets ---


def test_download_node_sets(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = download_node_sets(circuit_id, mock_client, tmp_path)

    assert result == tmp_path / "node_sets.json"
    assert result.exists()
    # Called twice: once for circuit_config.json (temp), once for node_sets.json
    assert mock_client.fetch_file.call_count == 2


# --- download_mechanisms ---


def test_download_mechanisms_success(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)
    mock_client.list_directory.return_value = _make_file_list(CIRCUIT_DIR)

    result = download_mechanisms(circuit_id, mock_client, tmp_path)

    assert len(result) == 15
    for path in result:
        assert path.suffix == ".mod"
        assert path.parent == tmp_path


def test_download_mechanisms_no_mod_files(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)
    file_list = Mock()
    file_list.files = {}
    mock_client.list_directory.return_value = file_list

    with pytest.raises(FileNotFoundError, match=r"No \.mod files found"):
        download_mechanisms(circuit_id, mock_client, tmp_path)


# --- download_electrical_models ---


def test_download_electrical_models_all_populations(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)
    mock_client.list_directory.return_value = _make_file_list(CIRCUIT_DIR)

    result = download_electrical_models(circuit_id, mock_client, tmp_path)

    assert len(result) == 2
    for path in result:
        assert path.suffix == ".hoc"


def test_download_electrical_models_specific_population(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)
    mock_client.list_directory.return_value = _make_file_list(CIRCUIT_DIR)

    result = download_electrical_models(
        circuit_id, mock_client, tmp_path, node_population="S1nonbarrel_neurons"
    )

    assert len(result) == 2
    for path in result:
        assert path.suffix == ".hoc"
        assert path.parent == tmp_path


def test_download_electrical_models_invalid_population(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    with pytest.raises(ValueError, match="not found"):
        download_electrical_models(circuit_id, mock_client, tmp_path, node_population="nonexistent")


def test_download_electrical_models_no_hoc_files(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)
    file_list = Mock()
    file_list.files = {}
    mock_client.list_directory.return_value = file_list

    with pytest.raises(FileNotFoundError, match=r"No \.hoc files found"):
        download_electrical_models(
            circuit_id, mock_client, tmp_path, node_population="S1nonbarrel_neurons"
        )


# --- download_node_populations ---


def test_download_node_populations_all(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = download_node_populations(circuit_id, mock_client, tmp_path)

    # 3 populations: S1nonbarrel_neurons, POm, VPM
    assert len(result) == 3
    for path in result:
        assert path.name == "nodes.h5"


def test_download_node_populations_specific(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = download_node_populations(
        circuit_id, mock_client, tmp_path, node_population="S1nonbarrel_neurons"
    )

    assert len(result) == 1
    assert result[0].name == "nodes.h5"
    assert result[0].parent == tmp_path


def test_download_node_populations_invalid(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    with pytest.raises(ValueError, match="not found"):
        download_node_populations(circuit_id, mock_client, tmp_path, node_population="nonexistent")


# --- download_edge_populations ---


def test_download_edge_populations_all(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = download_edge_populations(circuit_id, mock_client, tmp_path)

    assert len(result) == 3
    for path in result:
        assert path.name == "edges.h5"


def test_download_edge_populations_specific(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = download_edge_populations(
        circuit_id,
        mock_client,
        tmp_path,
        edge_population="S1nonbarrel_neurons__S1nonbarrel_neurons__chemical",
    )

    assert len(result) == 1
    assert result[0].name == "edges.h5"
    assert result[0].parent == tmp_path


def test_download_edge_populations_invalid(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    with pytest.raises(ValueError, match="not found"):
        download_edge_populations(circuit_id, mock_client, tmp_path, edge_population="nonexistent")


# --- download_id_mapping ---


def test_download_id_mapping_from_root(mock_client, circuit_id, tmp_path):
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = download_id_mapping(circuit_id, mock_client, tmp_path)

    assert result == tmp_path / "id_mapping.json"
    assert result.exists()


def test_download_id_mapping_from_config(mock_client, circuit_id, tmp_path):
    """Test when id_mapping path is specified in components/provenance/id_mapping."""
    modified_dir = tmp_path / "circuit_source"
    shutil.copytree(CIRCUIT_DIR, modified_dir)
    config_path = modified_dir / "circuit_config.json"
    config = json.loads(config_path.read_text())
    config["components"]["provenance"] = {"id_mapping": "id_mapping.json"}
    config_path.write_text(json.dumps(config))

    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(modified_dir)

    result = download_id_mapping(circuit_id, mock_client, tmp_path / "output")

    assert result.name == "id_mapping.json"


# --- fetch_file ---


def test_fetch_file_default_strategy(mock_client, circuit_id, asset_id, tmp_path):
    """Test that fetch_file uses link_or_download by default."""
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = fetch_file(mock_client, circuit_id, asset_id, "circuit_config.json", tmp_path)

    assert result == tmp_path / "circuit_config.json"
    call_kwargs = mock_client.fetch_file.call_args.kwargs
    assert call_kwargs["strategy"].value == "link_or_download"


def test_fetch_file_writable_strategy(mock_client, circuit_id, asset_id, tmp_path):
    """Test that fetch_file uses copy_or_download when writable=True."""
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = fetch_file(
        mock_client, circuit_id, asset_id, "circuit_config.json", tmp_path, writable=True
    )

    assert result == tmp_path / "circuit_config.json"
    call_kwargs = mock_client.fetch_file.call_args.kwargs
    assert call_kwargs["strategy"].value == "copy_or_download"


def test_fetch_file_output_filename(mock_client, circuit_id, asset_id, tmp_path):
    """Test that output_filename overrides the default filename."""
    mock_client.fetch_file.side_effect = _make_fetch_file_side_effect(CIRCUIT_DIR)

    result = fetch_file(
        mock_client,
        circuit_id,
        asset_id,
        "circuit_config.json",
        tmp_path,
        output_filename="renamed.json",
    )

    assert result == tmp_path / "renamed.json"


# --- fetch_directory ---


def test_fetch_directory_default_strategy(mock_client, circuit_id, asset_id, tmp_path):
    """Test that fetch_directory uses link_or_download by default."""
    mock_client.fetch_directory.return_value = [tmp_path / "file1.h5", tmp_path / "file2.h5"]

    result = fetch_directory(mock_client, circuit_id, asset_id, tmp_path)

    assert len(result) == 2
    call_kwargs = mock_client.fetch_directory.call_args.kwargs
    assert call_kwargs["strategy"].value == "link_or_download"
    assert call_kwargs["ignore_directory_name"] is True


def test_fetch_directory_writable_strategy(mock_client, circuit_id, asset_id, tmp_path):
    """Test that fetch_directory uses copy_or_download when writable=True."""
    mock_client.fetch_directory.return_value = [tmp_path / "file1.h5"]

    result = fetch_directory(mock_client, circuit_id, asset_id, tmp_path, writable=True)

    assert len(result) == 1
    call_kwargs = mock_client.fetch_directory.call_args.kwargs
    assert call_kwargs["strategy"].value == "copy_or_download"


def test_fetch_directory_creates_dest_dir(mock_client, circuit_id, asset_id, tmp_path):
    """Test that fetch_directory creates the destination directory if it doesn't exist."""
    dest = tmp_path / "nested" / "output"
    mock_client.fetch_directory.return_value = []

    fetch_directory(mock_client, circuit_id, asset_id, dest)

    assert dest.exists()

"""Tests for obi_one.utils.circuit_customization.populations."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from bluepysnap import Circuit

from obi_one.utils.circuit_customization.populations import (
    _update_circuit_config,
    _update_edge_populations,
    _update_node_populations,
    _update_node_sets,
    create_modified_circuit,
)
from obi_one.utils.circuit_customization.validations.populations import (
    check_customized_circuit,
    check_electrical_models,
    check_input_files,
    check_morphologies,
)

CIRCUIT_DIR = Path("examples/data/tiny_circuits/N_10__top_nodes_dim6")


@pytest.fixture
def circuit_copy(tmp_path):
    """Create a writable copy of the tiny circuit."""
    dest = tmp_path / "circuit"
    shutil.copytree(CIRCUIT_DIR, dest)
    return dest


# --- check_input_files ---


def test_check_input_files_no_inputs():
    """Test that no inputs raises."""
    with pytest.raises(ValueError, match="No customization files provided"):
        check_input_files()


def test_check_input_files_valid_config(circuit_copy):
    """Test validation of a valid circuit config file."""
    config = circuit_copy / "circuit_config.json"
    result = check_input_files(new_circuit_config_path=config)
    assert result[0] == config
    assert result[1] is None
    assert result[2] is None
    assert result[3] is None


def test_check_input_files_wrong_config_name(circuit_copy):
    """Test that config with wrong name raises."""
    wrong_name = circuit_copy / "node_sets.json"
    with pytest.raises(ValueError, match=r"circuit_config\.json"):
        check_input_files(new_circuit_config_path=wrong_name)


def test_check_input_files_nonexistent_file():
    """Test that a nonexistent file raises."""
    with pytest.raises(ValueError, match="does not exist"):
        check_input_files(new_circuit_config_path="/nonexistent/circuit_config.json")


def test_check_input_files_valid_node_sets(circuit_copy):
    """Test validation of a valid node sets file."""
    node_sets = circuit_copy / "node_sets.json"
    result = check_input_files(new_node_sets_path=node_sets)
    assert result[1] == node_sets


def test_check_input_files_valid_node_population(circuit_copy):
    """Test validation of valid node population files."""
    nodes_h5 = circuit_copy / "S1nonbarrel_neurons" / "nodes.h5"
    result = check_input_files(new_node_population_paths={"S1nonbarrel_neurons": nodes_h5})
    assert result[2] == {"S1nonbarrel_neurons": nodes_h5}


def test_check_input_files_wrong_extension(circuit_copy):
    """Test that wrong file extension raises."""
    json_file = circuit_copy / "node_sets.json"
    with pytest.raises(ValueError, match=r"must be \.h5"):
        check_input_files(new_node_population_paths={"pop": json_file})


def test_check_input_files_valid_edge_population(circuit_copy):
    """Test validation of valid edge population files."""
    edges_h5 = circuit_copy / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical" / "edges.h5"
    result = check_input_files(
        new_edge_population_paths={"S1nonbarrel_neurons__S1nonbarrel_neurons__chemical": edges_h5}
    )
    assert result[3] is not None


# --- check_customized_circuit ---


def test_check_customized_circuit_valid(circuit_copy):
    """Test that a valid circuit passes validation."""
    check_customized_circuit(circuit_copy)


def test_check_customized_circuit_missing_config(tmp_path):
    """Test that a missing config raises."""
    with pytest.raises(ValueError, match="Failed to load"):
        check_customized_circuit(tmp_path)


def test_check_customized_circuit_missing_nodes(circuit_copy):
    """Test that missing node files raises."""
    (circuit_copy / "S1nonbarrel_neurons" / "nodes.h5").unlink()
    with pytest.raises(ValueError, match="Failed to load"):
        check_customized_circuit(circuit_copy)


# --- check_morphologies ---


def test_check_morphologies_valid(circuit_copy):
    """Test that identical circuits pass morphology check."""

    circuit = Circuit(circuit_copy / "circuit_config.json")
    check_morphologies(circuit, circuit)


def test_check_morphologies_extra_path(circuit_copy):
    """Test that extra morphology paths raise."""

    circuit = Circuit(circuit_copy / "circuit_config.json")

    # Parent with no populations -> new circuit has extra morph paths
    parent_mock = MagicMock(spec=Circuit)
    parent_nodes_mock = MagicMock()
    parent_nodes_mock.population_names = []
    parent_mock.nodes = parent_nodes_mock

    with pytest.raises(ValueError, match="Morphology path"):
        check_morphologies(circuit, parent_mock)


# --- check_electrical_models ---


def test_check_electrical_models_valid(circuit_copy):
    """Test that identical circuits pass electrical model check."""

    circuit = Circuit(circuit_copy / "circuit_config.json")
    check_electrical_models(circuit, circuit)


def test_check_electrical_models_extra_path(circuit_copy):
    """Test that extra hoc paths raise."""

    circuit = Circuit(circuit_copy / "circuit_config.json")

    # Parent with no populations -> new circuit has extra hoc paths
    parent_mock = MagicMock(spec=Circuit)
    parent_nodes_mock = MagicMock()
    parent_nodes_mock.population_names = []
    parent_mock.nodes = parent_nodes_mock

    with pytest.raises(ValueError, match=r"Electrical model \.hoc path"):
        check_electrical_models(circuit, parent_mock)


# --- create_modified_circuit (integration with mocked download) ---


def test_create_modified_circuit_replaces_node_sets(circuit_copy):
    """Test that node sets file gets replaced."""

    config_path = circuit_copy / "circuit_config.json"
    parent_circuit = Circuit(config_path)
    new_circuit = _update_circuit_config(config_path, None)

    # Create a custom node sets file outside the circuit folder
    custom_node_sets = circuit_copy.parent / "custom_node_sets.json"
    custom_node_sets.write_text(json.dumps({"custom_set": {"node_id": [0, 1, 2]}}))

    # Get the target path from the config
    node_sets_file = new_circuit.config.get("node_sets_file", "")
    assert node_sets_file  # should be set in our test circuit

    _update_node_sets(new_circuit, parent_circuit, custom_node_sets)

    # Verify the file was replaced
    with Path(node_sets_file).open(encoding="utf-8") as f:
        content = json.load(f)
    assert "custom_set" in content


def test_create_modified_circuit_node_sets_not_in_config(circuit_copy):
    """Test error when node sets file provided but not in config."""

    # Modify config to remove node_sets_file reference
    config_path = circuit_copy / "circuit_config.json"
    config = json.loads(config_path.read_text())
    del config["node_sets_file"]
    config_path.write_text(json.dumps(config))

    parent_circuit = Circuit(config_path)
    new_circuit = _update_circuit_config(config_path, None)

    custom_node_sets = circuit_copy.parent / "custom_node_sets.json"
    custom_node_sets.write_text(json.dumps({}))

    with pytest.raises(ValueError, match="not specified in circuit config"):
        _update_node_sets(new_circuit, parent_circuit, custom_node_sets)


def test_create_modified_circuit_replaces_node_population(circuit_copy):
    """Test that a node population file gets replaced."""

    config_path = circuit_copy / "circuit_config.json"
    parent_circuit = Circuit(config_path)
    new_circuit = _update_circuit_config(config_path, None)

    # Use the existing nodes.h5 as a "replacement" (just testing the copy logic)
    nodes_h5 = circuit_copy / "S1nonbarrel_neurons" / "nodes.h5"
    original_size = nodes_h5.stat().st_size

    # Create a dummy replacement file outside the circuit folder
    replacement = circuit_copy.parent / "replacement_nodes.h5"
    replacement.write_bytes(b"\x89HDF" + b"\x00" * 100)

    _update_node_populations(new_circuit, parent_circuit, {"S1nonbarrel_neurons": replacement})

    # The file should have been replaced
    assert nodes_h5.stat().st_size != original_size


def test_create_modified_circuit_unknown_population(circuit_copy):
    """Test error when unknown population name is provided."""

    config_path = circuit_copy / "circuit_config.json"
    parent_circuit = Circuit(config_path)
    new_circuit = _update_circuit_config(config_path, None)

    dummy = circuit_copy.parent / "dummy.h5"
    dummy.write_bytes(b"\x89HDF")

    with pytest.raises(ValueError, match="not found in circuit config"):
        _update_node_populations(new_circuit, parent_circuit, {"nonexistent_pop": dummy})


def test_create_modified_circuit_full_flow(circuit_copy):
    """Test the full create_modified_circuit flow with replaced populations."""

    mock_client = MagicMock()
    circuit_id = str(uuid4())

    # Mock get_sonata_asset to return a mock circuit entity and asset
    mock_circuit_entity = MagicMock()
    mock_asset = MagicMock()
    mock_asset.id = uuid4()

    # Mock fetch_directory to copy the real circuit
    output_path = circuit_copy.parent / "new_circuit"

    def mock_fetch_dir(_db_client, _cid, _asset_id, dest, *, writable=False):  # noqa: ARG001
        shutil.copytree(circuit_copy, dest)
        return list(dest.rglob("*"))

    # Prepare replacement files (copies of existing ones, simulating modified data)
    custom_nodes = circuit_copy.parent / "custom_nodes.h5"
    shutil.copy(circuit_copy / "S1nonbarrel_neurons" / "nodes.h5", custom_nodes)

    custom_edges = circuit_copy.parent / "custom_edges.h5"
    shutil.copy(
        circuit_copy / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical" / "edges.h5",
        custom_edges,
    )

    with (
        patch(
            "obi_one.utils.circuit_customization.populations.get_sonata_asset",
            return_value=(mock_circuit_entity, mock_asset),
        ),
        patch(
            "obi_one.utils.circuit_customization.populations.fetch_directory",
            side_effect=mock_fetch_dir,
        ),
    ):
        result_path, result_entity = create_modified_circuit(
            db_client=mock_client,
            circuit_id=circuit_id,
            new_node_sets_path=circuit_copy / "node_sets.json",
            new_node_population_paths={"S1nonbarrel_neurons": custom_nodes},
            new_edge_population_paths={
                "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical": custom_edges
            },
            new_circuit_path=output_path,
        )

    assert result_path == output_path
    assert result_entity is mock_circuit_entity
    assert (output_path / "circuit_config.json").exists()
    assert (output_path / "S1nonbarrel_neurons" / "nodes.h5").exists()
    assert (
        output_path / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical" / "edges.h5"
    ).exists()


def test_create_modified_circuit_new_populations(circuit_copy):
    """Test adding new populations with a custom config."""

    mock_client = MagicMock()
    circuit_id = str(uuid4())

    mock_circuit_entity = MagicMock()
    mock_asset = MagicMock()
    mock_asset.id = uuid4()

    output_path = circuit_copy.parent / "new_circuit"

    def mock_fetch_dir(_db_client, _cid, _asset_id, dest, *, writable=False):  # noqa: ARG001
        shutil.copytree(circuit_copy, dest)
        return list(dest.rglob("*"))

    # Create a custom circuit config that adds new populations
    config = json.loads((circuit_copy / "circuit_config.json").read_text())
    config["networks"]["nodes"].append(
        {
            "nodes_file": "$BASE_DIR/NewPop/nodes.h5",
            "populations": {"NewPop": {"type": "virtual"}},
        }
    )
    config["networks"]["edges"].append(
        {
            "edges_file": "$BASE_DIR/NewPop__S1nonbarrel_neurons__chemical/edges.h5",
            "populations": {"NewPop__S1nonbarrel_neurons__chemical": {"type": "chemical"}},
        }
    )
    custom_config = circuit_copy.parent / "circuit_config.json"
    custom_config.write_text(json.dumps(config))

    # Prepare custom population files
    custom_nodes = circuit_copy.parent / "custom_nodes.h5"
    shutil.copy(circuit_copy / "VPM" / "nodes.h5", custom_nodes)

    custom_edges = circuit_copy.parent / "custom_edges.h5"
    shutil.copy(
        circuit_copy / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical" / "edges.h5",
        custom_edges,
    )

    with (
        patch(
            "obi_one.utils.circuit_customization.populations.get_sonata_asset",
            return_value=(mock_circuit_entity, mock_asset),
        ),
        patch(
            "obi_one.utils.circuit_customization.populations.fetch_directory",
            side_effect=mock_fetch_dir,
        ),
        patch(
            "obi_one.utils.circuit_customization.populations.check_customized_circuit",
        ),
        patch(
            "obi_one.utils.circuit_customization.populations.check_morphologies",
        ),
        patch(
            "obi_one.utils.circuit_customization.populations.check_electrical_models",
        ),
    ):
        result_path, result_entity = create_modified_circuit(
            db_client=mock_client,
            circuit_id=circuit_id,
            new_circuit_config_path=custom_config,
            new_node_sets_path=circuit_copy / "node_sets.json",
            new_node_population_paths={"NewPop": custom_nodes},
            new_edge_population_paths={"NewPop__S1nonbarrel_neurons__chemical": custom_edges},
            new_circuit_path=output_path,
        )

    assert result_path == output_path
    assert result_entity is mock_circuit_entity
    assert (output_path / "NewPop" / "nodes.h5").exists()
    assert (output_path / "NewPop__S1nonbarrel_neurons__chemical" / "edges.h5").exists()
    # Original populations should still be there
    assert (output_path / "S1nonbarrel_neurons" / "nodes.h5").exists()


def test_create_modified_circuit_removes_node_sets(circuit_copy):
    """Test that node sets file is removed when not referenced in new config."""

    config_path = circuit_copy / "circuit_config.json"
    parent_circuit = Circuit(config_path)

    # Verify node sets file exists before
    node_sets_file = Path(parent_circuit.config.get("node_sets_file", ""))
    assert node_sets_file.is_file()

    # Create a new config without node_sets_file
    config = json.loads(config_path.read_text())
    del config["node_sets_file"]
    new_config = circuit_copy.parent / "circuit_config.json"
    new_config.write_text(json.dumps(config))

    # Apply the new config
    shutil.copy(new_config, config_path)
    new_circuit = Circuit(config_path)

    _update_node_sets(new_circuit, parent_circuit, None)

    # Node sets file should be deleted
    assert not node_sets_file.is_file()


def test_create_modified_circuit_removes_node_population(circuit_copy):
    """Test that node population files are removed when not referenced in new config."""

    config_path = circuit_copy / "circuit_config.json"
    parent_circuit = Circuit(config_path)

    # Verify VPM nodes file exists
    vpm_nodes = circuit_copy / "VPM" / "nodes.h5"
    assert vpm_nodes.is_file()

    # Create a new config that removes VPM population
    config = json.loads(config_path.read_text())
    config["networks"]["nodes"] = [
        n for n in config["networks"]["nodes"] if "VPM" not in n.get("populations", {})
    ]
    new_config = circuit_copy.parent / "circuit_config.json"
    new_config.write_text(json.dumps(config))

    # Apply the new config
    shutil.copy(new_config, config_path)
    new_circuit = Circuit(config_path)

    _update_node_populations(new_circuit, parent_circuit, None)

    # VPM nodes file should be deleted
    assert not vpm_nodes.is_file()
    # S1nonbarrel_neurons nodes should still exist
    assert (circuit_copy / "S1nonbarrel_neurons" / "nodes.h5").is_file()


def test_create_modified_circuit_removes_edge_population(circuit_copy):
    """Test that edge population files are removed when not referenced in new config."""

    config_path = circuit_copy / "circuit_config.json"
    parent_circuit = Circuit(config_path)

    # Verify POm edge file exists
    pom_edges = circuit_copy / "POm__S1nonbarrel_neurons__chemical" / "edges.h5"
    assert pom_edges.is_file()

    # Create a new config that removes POm edge population
    config = json.loads(config_path.read_text())
    config["networks"]["edges"] = [
        e
        for e in config["networks"]["edges"]
        if "POm__S1nonbarrel_neurons__chemical" not in e.get("populations", {})
    ]
    new_config = circuit_copy.parent / "circuit_config.json"
    new_config.write_text(json.dumps(config))

    # Apply the new config
    shutil.copy(new_config, config_path)
    new_circuit = Circuit(config_path)

    _update_edge_populations(new_circuit, parent_circuit, None)

    # POm edges file should be deleted
    assert not pom_edges.is_file()
    # Other edge files should still exist
    assert (
        circuit_copy / "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical" / "edges.h5"
    ).is_file()

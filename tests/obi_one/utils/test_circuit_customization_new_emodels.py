"""Tests for obi_one.utils.circuit_customization.new_emodels."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import h5py
import pytest

from obi_one.utils.circuit_customization.new_emodels import (
    create_modified_circuit,
    get_all_emodel_file_paths,
    get_biophysical_population,
    hoc_morph_names,
    map_ids_to_updated_memodel,
)
from obi_one.utils.circuit_customization.validations.new_emodels import read_node_file

from tests.utils import CIRCUIT_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"
DATA_FOLDER_PATH = Path(__file__).parent.parent.parent / "test_data"
NODES_FILE_PATH = DATA_FOLDER_PATH / "nodes.h5"


def _copy_circuit(tmp_path: Path, circuit_name: str = CIRCUIT_NAME) -> Path:
    """Copy a tiny test circuit into tmp_path."""
    dest = tmp_path / circuit_name
    shutil.copytree(CIRCUIT_DIR / circuit_name, dest)
    return dest


DYNAMICS_PARAMS = {
    "holding_current": 0.1,
    "resting_potential": -70.0,
    "input_resistance": 100.0,
    "threshold_current": 0.5,
}


def test_hoc_morph_names():
    """Test extraction of hoc and morphology names from a node population."""
    node_pop = read_node_file(NODES_FILE_PATH)
    hoc_fname, morph_stem = hoc_morph_names(node_pop, 0)

    assert hoc_fname == "cACint_L23MC.hoc"
    assert morph_stem == "sm110120c1-2_INT_idC_-_Scale_x1.000_y1.025_z1.000_-_Clone_0"


def test_map_ids_to_updated_memodel_no_changes():
    """Test that identical nodes files produce empty mappings."""
    old_mapping, new_mapping, new_to_old = map_ids_to_updated_memodel(
        NODES_FILE_PATH,
        NODES_FILE_PATH,
        [],
    )

    assert old_mapping == {}
    assert new_mapping == {}
    assert new_to_old == {}


def test_map_ids_to_updated_memodel_template_change(tmp_path):
    """Test detection when model_template changes between old and new nodes."""
    new_nodes = tmp_path / "new_nodes.h5"
    shutil.copy(NODES_FILE_PATH, new_nodes)
    with h5py.File(new_nodes, "r+") as f:
        f["nodes/S1nonbarrel_neurons/0/model_template"][0] = b"hoc:new_template"

    new_hoc = tmp_path / "new_template.hoc"
    new_hoc.touch()

    old_mapping, new_mapping, new_to_old = map_ids_to_updated_memodel(
        NODES_FILE_PATH,
        new_nodes,
        [new_hoc],
    )

    assert 0 in old_mapping
    assert 0 in new_mapping
    assert new_mapping[0] == ("new_template.hoc", old_mapping[0][1])
    assert new_to_old[new_mapping[0]] == old_mapping[0]


def test_map_ids_to_updated_memodel_same_name_new_file(tmp_path):
    """Test detection when template name is unchanged but a new hoc file is provided."""
    new_nodes = tmp_path / "new_nodes.h5"
    shutil.copy(NODES_FILE_PATH, new_nodes)
    new_hoc = tmp_path / "cACint_L23MC.hoc"
    new_hoc.touch()

    old_mapping, new_mapping, new_to_old = map_ids_to_updated_memodel(
        NODES_FILE_PATH,
        new_nodes,
        [new_hoc],
    )

    assert 0 in old_mapping
    assert 0 in new_mapping
    assert old_mapping[0] == new_mapping[0]
    assert new_to_old[new_mapping[0]] == old_mapping[0]


def test_get_all_emodel_file_paths(tmp_path):
    """Test collection of emodel file paths required by a nodes file."""
    emodels_dir = tmp_path / "emodels_hoc"
    emodels_dir.mkdir()

    paths = get_all_emodel_file_paths(NODES_FILE_PATH, emodels_dir)

    assert paths == {
        emodels_dir / "cACint_L23MC.hoc",
        emodels_dir / "cADpyr_L2TPC.hoc",
    }


def test_get_biophysical_population(tmp_path):
    """Test opening the single biophysical population from a tiny circuit."""
    circuit_path = _copy_circuit(tmp_path)

    pop = get_biophysical_population(circuit_path)

    assert pop.name == "S1nonbarrel_neurons"
    assert pop.type == "biophysical"


@patch("obi_one.utils.circuit_customization.new_emodels.bluepysnap.Circuit")
def test_get_biophysical_population_raises_when_missing(mock_circuit, tmp_path):
    """Test error when no biophysical population exists."""
    virtual_pop = MagicMock()
    virtual_pop.type = "virtual"
    mock_circuit.return_value.nodes.values.return_value = [virtual_pop]

    with pytest.raises(
        AssertionError, match="Expected one and only one biophysical population, found 0"
    ):
        get_biophysical_population(tmp_path / "circuit")


@patch("obi_one.utils.circuit_customization.new_emodels.compile_mechanisms")
@patch("obi_one.utils.circuit_customization.new_emodels.clean_compiled_mechanisms")
@patch("bluecellulab.tools.compute_memodel_properties_v2", create=True)
@patch("bluecellulab.tools.calculate_SS_voltage")
def test_create_modified_circuit(
    mock_calc_ss_voltage,
    mock_compute_memodel_properties,
    mock_clean_mechs,
    mock_compile_mechs,
    tmp_path,
):
    """Test end-to-end circuit customization with mocked bluecellulab computations."""
    parent_circuit = _copy_circuit(tmp_path)
    parent_nodes = parent_circuit / "S1nonbarrel_neurons" / "nodes.h5"

    new_nodes = tmp_path / "new_nodes.h5"
    shutil.copy(parent_nodes, new_nodes)
    new_hoc = tmp_path / "cACint_L23MC.hoc"
    new_hoc.write_text("// modified hoc")

    mock_calc_ss_voltage.return_value = -70.0
    mock_compute_memodel_properties.return_value = DYNAMICS_PARAMS

    new_circuit_path = tmp_path / "updated_circuit"
    result = create_modified_circuit(
        parent_circuit_path=parent_circuit,
        new_nodes_file_path=new_nodes,
        new_emodels_file_paths=[new_hoc],
        new_circuit_path=new_circuit_path,
    )

    assert result == new_circuit_path
    assert (new_circuit_path / "circuit_config.json").exists()
    assert (new_circuit_path / "emodels_hoc" / "cACint_L23MC.hoc").read_text() == "// modified hoc"
    assert (new_circuit_path / "emodels_hoc" / "cADpyr_L6BPC.hoc").exists()
    mock_clean_mechs.assert_called_once()
    mock_compile_mechs.assert_called_once()

    output_nodes = new_circuit_path / "S1nonbarrel_neurons" / "nodes.h5"
    output_pop = read_node_file(output_nodes)
    assert output_pop.get_attribute("model_template", 0) == "hoc:cACint_L23MC"
    with h5py.File(output_nodes) as nodes:
        dynamics = nodes["nodes/S1nonbarrel_neurons/0/dynamics_params"]
        assert dynamics["holding_current"][0] == pytest.approx(DYNAMICS_PARAMS["holding_current"])
        assert dynamics["resting_potential"][0] == pytest.approx(
            DYNAMICS_PARAMS["resting_potential"]
        )
        assert dynamics["input_resistance"][0] == pytest.approx(DYNAMICS_PARAMS["input_resistance"])
        assert dynamics["threshold_current"][0] == pytest.approx(
            DYNAMICS_PARAMS["threshold_current"]
        )
        mecombo = nodes["nodes/S1nonbarrel_neurons/0/me_combo"][0].decode()
        assert mecombo.startswith("cACint_L23MC_")


@patch("obi_one.utils.circuit_customization.new_emodels.compile_mechanisms")
@patch("obi_one.utils.circuit_customization.new_emodels.clean_compiled_mechanisms")
@patch("bluecellulab.tools.compute_memodel_properties_v2", create=True)
@patch("bluecellulab.tools.calculate_SS_voltage")
def test_create_modified_circuit_with_new_template(
    mock_calc_ss_voltage,
    mock_compute_memodel_properties,
    mock_clean_mechs,
    mock_compile_mechs,
    tmp_path,
):
    """Test circuit customization when the nodes file declares a new model template."""
    parent_circuit = _copy_circuit(tmp_path)
    parent_nodes = parent_circuit / "S1nonbarrel_neurons" / "nodes.h5"
    new_template = "new_template"

    new_nodes = tmp_path / "new_nodes.h5"
    shutil.copy(parent_nodes, new_nodes)
    with h5py.File(new_nodes, "r+") as nodes:
        nodes["nodes/S1nonbarrel_neurons/0/@library/model_template"][0] = b"hoc:new_template"

    new_hoc = tmp_path / f"{new_template}.hoc"
    new_hoc.write_text("// new template hoc")

    mock_calc_ss_voltage.return_value = -70.0
    mock_compute_memodel_properties.return_value = DYNAMICS_PARAMS

    new_circuit_path = tmp_path / "updated_circuit"
    result = create_modified_circuit(
        parent_circuit_path=parent_circuit,
        new_nodes_file_path=new_nodes,
        new_emodels_file_paths=[new_hoc],
        new_circuit_path=new_circuit_path,
    )

    assert result == new_circuit_path
    assert (
        new_circuit_path / "emodels_hoc" / f"{new_template}.hoc"
    ).read_text() == "// new template hoc"
    assert not (new_circuit_path / "emodels_hoc" / "cACint_L23MC.hoc").exists()
    assert (new_circuit_path / "emodels_hoc" / "cADpyr_L6BPC.hoc").exists()
    mock_clean_mechs.assert_called_once()
    mock_compile_mechs.assert_called_once()

    output_nodes = new_circuit_path / "S1nonbarrel_neurons" / "nodes.h5"
    output_pop = read_node_file(output_nodes)
    assert output_pop.get_attribute("model_template", 0) == f"hoc:{new_template}"
    with h5py.File(output_nodes) as nodes:
        dynamics = nodes["nodes/S1nonbarrel_neurons/0/dynamics_params"]
        assert dynamics["holding_current"][0] == pytest.approx(DYNAMICS_PARAMS["holding_current"])
        assert dynamics["resting_potential"][0] == pytest.approx(
            DYNAMICS_PARAMS["resting_potential"]
        )
        assert dynamics["input_resistance"][0] == pytest.approx(DYNAMICS_PARAMS["input_resistance"])
        assert dynamics["threshold_current"][0] == pytest.approx(
            DYNAMICS_PARAMS["threshold_current"]
        )
        mecombo = nodes["nodes/S1nonbarrel_neurons/0/me_combo"][0].decode()
        assert mecombo.startswith(f"{new_template}_")


def test_create_modified_circuit_raises_if_path_exists(tmp_path):
    """Test error when the target circuit directory already exists."""
    parent_circuit = _copy_circuit(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()

    with (
        patch("bluecellulab.tools.compute_memodel_properties_v2", create=True),
        patch("bluecellulab.tools.calculate_SS_voltage"),
        pytest.raises(AssertionError, match="already exists"),
    ):
        create_modified_circuit(
            parent_circuit_path=parent_circuit,
            new_nodes_file_path=parent_circuit / "S1nonbarrel_neurons" / "nodes.h5",
            new_emodels_file_paths=[],
            new_circuit_path=existing,
        )

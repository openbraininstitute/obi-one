"""Test validations of circuit customization."""

import shutil
from pathlib import Path

import h5py
import pytest

from obi_one.utils.circuit_customization.validations.new_emodels import (
    check_hoc_files_exist,
    check_new_hoc_in_nodes_file,
    check_new_node_columns,
    read_node_file,
)

DATA_FOLDER_PATH = Path(__file__).parent.parent.parent / "test_data"
NODES_FILE_PATH = DATA_FOLDER_PATH / "nodes.h5"


def test_check_new_node_columns(tmp_path):
    """Test check_new_node_columns."""
    new_node_fpath = tmp_path / "new_nodes.h5"

    # identical case: pass
    check_new_node_columns(NODES_FILE_PATH, NODES_FILE_PATH)

    # allowed modification: pass
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, "r+") as new_node:
        new_node["nodes/S1nonbarrel_neurons/0/model_template"][0] = b"hoc:new_template"
        new_node["nodes/S1nonbarrel_neurons/0/etype"][0] = b"hoc:new_etype"
    check_new_node_columns(NODES_FILE_PATH, new_node_fpath)

    # new attribute name: fail
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, "r+") as new_node:
        group = new_node["nodes/S1nonbarrel_neurons/0/"]
        group.create_dataset("new_attribute", data=[0, 1])
    with pytest.raises(ValueError, match="attribute names"):
        check_new_node_columns(NODES_FILE_PATH, new_node_fpath)

    # missing attribute name: fail
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, "r+") as new_node:
        del new_node["nodes/S1nonbarrel_neurons/0/model_template"]
    with pytest.raises(ValueError, match="attribute names"):
        check_new_node_columns(NODES_FILE_PATH, new_node_fpath)

    # unallowed modification: fail
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, "r+") as new_node:
        new_node["nodes/S1nonbarrel_neurons/0/mtype"][0] = b"hoc:new_mtype"
    with pytest.raises(ValueError, match="mtype"):
        check_new_node_columns(NODES_FILE_PATH, new_node_fpath)


def test_check_hoc_files_exist(tmp_path):
    """Test check_hoc_files_exist."""
    old_hoc_dir = tmp_path / "old_hocs"
    new_hoc_dir = tmp_path / "new_hocs"
    old_hoc_dir.mkdir()
    new_hoc_dir.mkdir()

    with pytest.raises(FileNotFoundError):
        check_hoc_files_exist(NODES_FILE_PATH, old_hoc_dir, new_hoc_dir)

    # create hoc files in one dir
    node_pop = read_node_file(NODES_FILE_PATH)
    selection = node_pop.select_all()
    templates = set(node_pop.get_attribute("model_template", selection))
    templates_names = {temp.split(":", 1)[1] for temp in templates}
    for temp in templates_names:
        (old_hoc_dir / f"{temp}.hoc").touch()

    # should pass since all hoc files exist
    check_hoc_files_exist(NODES_FILE_PATH, old_hoc_dir, new_hoc_dir)

    # remove hoc files from directory and add them to new dir and check again
    for temp in templates_names:
        (old_hoc_dir / f"{temp}.hoc").unlink()
        (new_hoc_dir / f"{temp}.hoc").touch()
    check_hoc_files_exist(NODES_FILE_PATH, old_hoc_dir, new_hoc_dir)


def test_check_new_hoc_in_nodes_file(tmp_path):
    """Test check_new_hoc_in_nodes_file."""
    # unexpected hoc case
    unexpected_hoc = tmp_path / "unexpected_template.hoc"
    unexpected_hoc.touch()
    with pytest.raises(ValueError, match="not declared"):
        check_new_hoc_in_nodes_file(NODES_FILE_PATH, [unexpected_hoc])

    # has the right stem but is not a hoc case
    not_a_hoc = tmp_path / "cACint_L23MC.txt"
    not_a_hoc.touch()
    with pytest.raises(ValueError, match=r"\.hoc extension"):
        check_new_hoc_in_nodes_file(NODES_FILE_PATH, [not_a_hoc])

    # all hocs are declared in nodes file case
    hoc1 = tmp_path / "cACint_L23MC.hoc"
    hoc1.touch()
    hoc2 = tmp_path / "cADpyr_L2TPC.hoc"
    hoc2.touch()
    check_new_hoc_in_nodes_file(NODES_FILE_PATH, [hoc1, hoc2])

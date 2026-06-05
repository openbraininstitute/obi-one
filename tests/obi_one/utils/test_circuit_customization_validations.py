"""Test validations of circuit customization."""

from pathlib import Path
import shutil

import h5py
import pytest

from obi_one.utils.circuit_customization.validations.new_emodels import check_new_node_columns


DATA_FOLDER_PATH = Path(__file__).parent.parent.parent / "test_data"
NODES_FILE_PATH = DATA_FOLDER_PATH / "nodes.h5"


def test_check_new_node_columns(tmp_path):
    """Test check_new_node_columns."""
    new_node_fpath = tmp_path / "new_nodes.h5"

    # identical case: pass
    check_new_node_columns(NODES_FILE_PATH, NODES_FILE_PATH)

    # allowed modification: pass
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, 'r+') as new_node:
        new_node["nodes/S1nonbarrel_neurons/0/model_template"][0] = b"hoc:new_template"
        new_node["nodes/S1nonbarrel_neurons/0/etype"][0] = b"hoc:new_etype"
    check_new_node_columns(NODES_FILE_PATH, new_node_fpath)

    # new attribute name: fail
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, 'r+') as new_node:
        group = new_node["nodes/S1nonbarrel_neurons/0/"]
        group.create_dataset("new_attribute", data=[0, 1])
    with pytest.raises(AssertionError):
        check_new_node_columns(NODES_FILE_PATH, new_node_fpath)

    # missing attribute name: fail
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, 'r+') as new_node:
        del new_node["nodes/S1nonbarrel_neurons/0/model_template"]
    with pytest.raises(AssertionError):
        check_new_node_columns(NODES_FILE_PATH, new_node_fpath)

    # unallowed modification: fail
    shutil.copy(NODES_FILE_PATH, new_node_fpath)
    with h5py.File(new_node_fpath, 'r+') as new_node:
        new_node["nodes/S1nonbarrel_neurons/0/mtype"][0] = b"hoc:new_mtype"
    with pytest.raises(AssertionError):
        check_new_node_columns(NODES_FILE_PATH, new_node_fpath)

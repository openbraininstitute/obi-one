"""Tests for circuit utility functions (asset generation)."""

import json
import shutil

import pytest

from obi_one.core.exception import OBIONEError
from obi_one.utils.circuit import (
    run_basic_connectivity_plots,
    run_circuit_folder_compression,
    run_connectivity_matrix_extraction,
)

from tests.utils import CIRCUIT_DIR, MATRIX_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"
EDGE_POPULATION = "S1nonbarrel_neurons__S1nonbarrel_neurons__chemical"


def _copy_circuit(tmp_path, circuit_name=CIRCUIT_NAME):
    """Copy a test circuit into tmp_path for writable output.

    Returns the circuit_config.json path inside the copied structure.
    Layout: tmp_path / circuit_name / ...
    so that circuit_path.parents[1] == tmp_path (used as output_root).
    """
    dest = tmp_path / circuit_name
    shutil.copytree(CIRCUIT_DIR / circuit_name, dest)
    return dest / "circuit_config.json"


def test_run_circuit_folder_compression(tmp_path):
    """Test folder compression of a tiny circuit."""
    circuit_path = _copy_circuit(tmp_path)

    result = run_circuit_folder_compression(
        circuit_path=circuit_path,
        circuit_name="test_compressed",
        output_root=tmp_path,
    )
    assert result.exists()
    assert result.suffix == ".gz"
    assert result.stat().st_size > 0


def test_run_connectivity_matrix_extraction(tmp_path):
    """Test connectivity matrix extraction from a tiny circuit."""
    circuit_path = _copy_circuit(tmp_path)

    output_dir, config_file, edge_pop = run_connectivity_matrix_extraction(
        circuit_path=circuit_path,
        output_root=tmp_path,
    )
    assert output_dir.is_dir()
    assert config_file.exists()
    assert config_file.name == "matrix_config.json"
    assert len(edge_pop) > 0

    with config_file.open() as f:
        config = json.load(f)
    assert edge_pop in config


def test_run_basic_connectivity_plots(tmp_path):
    """Test basic connectivity plot generation from a connectivity matrix."""
    # Set up a circuit_path (only used for naming, not for reading circuit data)
    circuit_dir = tmp_path / CIRCUIT_NAME
    circuit_dir.mkdir()

    # Set up matrix config pointing to existing test matrix
    matrix_dir = tmp_path / (CIRCUIT_NAME + "__CONN_MATRIX__")
    matrix_dir.mkdir()
    shutil.copy(MATRIX_DIR / CIRCUIT_NAME / "connectivity_matrix.h5", matrix_dir)
    matrix_config = matrix_dir / "matrix_config.json"
    matrix_config.write_text(
        json.dumps({EDGE_POPULATION: {"single": {"path": "connectivity_matrix.h5"}}})
    )

    plot_dir, plot_files = run_basic_connectivity_plots(
        matrix_config=matrix_config,
        edge_population=EDGE_POPULATION,
        output_root=tmp_path,
    )
    assert plot_dir.is_dir()
    assert len(plot_files) > 0
    for f in plot_files:
        assert (plot_dir / f).is_file()


def test_run_basic_connectivity_plots_missing_config(tmp_path):
    """Test error when matrix config file is missing."""
    with pytest.raises(OBIONEError, match=r"Connectivity matrix config file.*not found"):
        run_basic_connectivity_plots(
            matrix_config=tmp_path / "nonexistent" / "matrix_config.json",
            edge_population="default",
            output_root=tmp_path,
        )


def test_run_basic_connectivity_plots_missing_matrix(tmp_path):
    """Test error when matrix h5 file is missing."""
    config = tmp_path / "matrix_config.json"
    config.write_text('{"default": {"single": {"path": "missing.h5"}}}')

    with pytest.raises(OBIONEError, match=r"Connectivity matrix file.*not found"):
        run_basic_connectivity_plots(
            matrix_config=config,
            edge_population="default",
            output_root=tmp_path,
        )

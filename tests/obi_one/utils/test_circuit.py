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

from tests.utils import CIRCUIT_DIR, MATRIX_DIR, SINGLE_NEURON_CIRCUIT_DIR

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


from obi_one.scientific.library.circuit import Circuit
from obi_one.utils.circuit import get_circuit_size


def test_get_circuit_size_small_circuit():
    """Test scale and counts for a small (10-neuron) circuit."""
    circuit_path = str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json")
    c = Circuit(name="test_small", path=circuit_path)

    scale, num_nrn, num_syn, num_conn = get_circuit_size(c)

    assert scale == "small"
    assert num_nrn == 10
    assert num_syn > 0
    assert num_conn > 0
    assert num_conn <= num_syn  # connections <= synapses


def test_get_circuit_size_pair_circuit():
    """Test scale and counts for a pair (2-neuron) circuit."""
    circuit_path = str(
        CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5" / "circuit_config.json"
    )
    c = Circuit(name="test_pair", path=circuit_path)

    scale, num_nrn, num_syn, num_conn = get_circuit_size(c)

    assert scale == "pair"
    assert num_nrn == 2
    assert num_syn > 0
    assert num_conn > 0


def test_get_circuit_size_single_neuron_circuit():
    """Test scale and counts for a single-neuron circuit."""
    circuit_path = str(
        SINGLE_NEURON_CIRCUIT_DIR
        / "SingleNeuronCircuit__top_nodes_dim6__IDX0"
        / "circuit_config.json"
    )
    c = Circuit(name="test_single", path=circuit_path)

    scale, num_nrn, num_syn, num_conn = get_circuit_size(c)

    assert scale == "single"
    assert num_nrn == 1


from obi_one.utils.circuit import run_validation


def test_run_validation_circuit_with_errors():
    """Test that validation raises for a circuit with known datatype issues."""
    circuit_path = str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json")
    with pytest.raises(ValueError, match="Circuit validation error"):
        run_validation(circuit_path)


def test_run_validation_invalid_path(tmp_path):
    """Test that validation raises for a non-existent circuit."""
    with pytest.raises(Exception):
        run_validation(str(tmp_path / "nonexistent" / "circuit_config.json"))


from PIL import Image

from obi_one.utils.circuit import generate_overview_figure


def test_generate_overview_figure_fallback_template(tmp_path):
    """Test that template is used when no plots directory is provided."""
    output_file = tmp_path / "overview.png"

    result = generate_overview_figure(basic_plots_dir=None, output_file=output_file)

    assert result == output_file
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_generate_overview_figure_fallback_when_no_circular_plot(tmp_path):
    """Test that template is used when plots dir exists but has no circular plot."""
    plots_dir = tmp_path / "plots"
    plots_dir.mkdir()
    output_file = tmp_path / "overview.png"

    result = generate_overview_figure(basic_plots_dir=plots_dir, output_file=output_file)

    assert result == output_file
    assert output_file.exists()
    assert output_file.stat().st_size > 0


def test_generate_overview_figure_with_circular_plot(tmp_path):
    """Test that circular plot is used when available."""
    plots_dir = tmp_path / "plots"
    plots_dir.mkdir()
    # Create a dummy circular plot image
    img = Image.new("RGB", (123, 123), color="blue")
    img.save(plots_dir / "small_network_in_2D_circular.png")

    output_file = tmp_path / "overview.png"
    result = generate_overview_figure(basic_plots_dir=plots_dir, output_file=output_file)

    assert result == output_file
    assert output_file.exists()
    assert output_file.stat().st_size > 0
    img = Image.open(output_file)
    assert img.width == 123


def test_generate_overview_figure_with_circular_and_table(tmp_path):
    """Test that circular plot and table are merged when both available."""
    plots_dir = tmp_path / "plots"
    plots_dir.mkdir()
    # Create dummy images
    img1 = Image.new("RGB", (123, 123), color="blue")
    img1.save(plots_dir / "small_network_in_2D_circular.png")
    img2 = Image.new("RGB", (321, 123), color="red")
    img2.save(plots_dir / "property_table_extra.png")

    output_file = tmp_path / "overview.png"
    result = generate_overview_figure(basic_plots_dir=plots_dir, output_file=output_file)

    assert result == output_file
    assert output_file.exists()
    # Merged image should be wider than either input
    merged = Image.open(output_file)
    assert merged.width == 444  # 123 + 321


def test_generate_overview_figure_raises_if_output_exists(tmp_path):
    """Test that error is raised when output file already exists."""
    from obi_one.core.exception import OBIONEError

    # Create a dummy output image
    output_file = tmp_path / "overview.png"
    img = Image.new("RGB", (123, 123), color="blue")
    img.save(output_file)

    with pytest.raises(OBIONEError, match="already exists"):
        generate_overview_figure(basic_plots_dir=None, output_file=output_file)


from obi_one.utils.circuit import get_circuit_properties


def test_get_circuit_properties_small_circuit():
    """Test properties for a small biophysical circuit with morphologies and e-models."""
    circuit_path = str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json")
    c = Circuit(name="test_small", path=circuit_path)

    has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
        get_circuit_properties(c)
    )

    assert has_morphologies is True
    assert has_point_neurons is False
    assert has_electrical_cell_models is True
    assert has_spines is False


def test_get_circuit_properties_pair_circuit():
    """Test properties for a pair circuit with morphologies and e-models."""
    circuit_path = str(
        CIRCUIT_DIR / "nbS1-O1-E2Sst-maxNsyn-HEX0-L5" / "circuit_config.json"
    )
    c = Circuit(name="test_pair", path=circuit_path)

    has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
        get_circuit_properties(c)
    )

    assert has_morphologies is True
    assert has_point_neurons is False
    assert has_electrical_cell_models is True
    assert has_spines is False


def test_get_circuit_properties_single_neuron_circuit():
    """Test properties for a single-neuron circuit (with empty virtual populations)."""
    circuit_path = str(
        SINGLE_NEURON_CIRCUIT_DIR
        / "SingleNeuronCircuit__top_nodes_dim6__IDX0"
        / "circuit_config.json"
    )
    c = Circuit(name="test_single", path=circuit_path)

    has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines = (
        get_circuit_properties(c)
    )

    assert has_morphologies is True
    assert has_point_neurons is False
    assert has_electrical_cell_models is True
    assert has_spines is False

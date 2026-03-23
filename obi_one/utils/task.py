"""Utility functions for running sub-tasks."""

import json
import logging
from pathlib import Path

from conntility import ConnectivityMatrix

from obi_one.core.exception import OBIONEError
from obi_one.core.path import NamedPath
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import _MAX_SMALL_MICROCIRCUIT_SIZE
from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsScanConfig,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionScanConfig,
)
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionScanConfig,
)

L = logging.getLogger(__name__)


def run_circuit_folder_compression(circuit_path: Path, circuit_name: str) -> Path:
    """Set up and run folder compression task."""
    # Import here to avoid circular import
    from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
    from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415

    # Set up circuit folder compression
    folder_path = NamedPath(
        name=circuit_path.parent.name + "__COMPRESSED__",  # Used as output name
        path=str(circuit_path.parent),
    )
    compression_init = FolderCompressionScanConfig.Initialize(
        folder_path=[folder_path],
        file_format="gz",
        file_name="circuit",
        archive_name=circuit_name,
    )
    folder_compressions_config = FolderCompressionScanConfig(initialize=compression_init)

    # Run circuit folder compression
    grid_scan = GridScanGenerationTask(
        form=folder_compressions_config,
        output_root=circuit_path.parents[1],
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    # Check and return output file
    output_file = (
        grid_scan.single_configs[0].coordinate_output_root
        / f"{compression_init.file_name}.{compression_init.file_format}"
    )
    if not output_file.exists():
        msg = "Compressed circuit file does not exist!"
        raise OBIONEError(msg)
    L.info(f"Circuit folder compressed into {output_file}")
    return output_file


def run_connectivity_matrix_extraction(circuit_path: Path) -> tuple[Path, Path, str]:
    """Set up and run connectivity matrix extraction task."""
    # Import here to avoid circular import
    from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
    from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415

    # Set up connectivity matrix extraction
    circuit = Circuit(
        name=circuit_path.parent.name + "__CONN_MATRIX__",  # Used as output name
        path=str(circuit_path),
    )
    edge_population = circuit.default_edge_population_name
    matrix_init = ConnectivityMatrixExtractionScanConfig.Initialize(
        circuit=[circuit],
        edge_population=edge_population,
        node_attributes=("synapse_class", "layer", "mtype", "etype", "x", "y", "z"),
        with_matrix_config=True,
    )
    matrix_extraction_config = ConnectivityMatrixExtractionScanConfig(initialize=matrix_init)

    # Run connectivity matrix extraction
    grid_scan = GridScanGenerationTask(
        form=matrix_extraction_config,
        output_root=circuit_path.parents[1],
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    # Check and return output directory
    output_dir = grid_scan.single_configs[0].coordinate_output_root
    output_file = output_dir / "matrix_config.json"
    if not output_file.exists():
        msg = "Connectivity matrix config file does not exist!"
        raise OBIONEError(msg)
    L.info(f"Connectivity matrix extracted to {output_dir}")
    return output_dir, output_file, edge_population


def run_basic_connectivity_plots(
    circuit_path: Path, matrix_config: Path, edge_population: str
) -> tuple[Path, list]:
    """Set up and run basic connectivity plotting task."""
    # Import here to avoid circular import
    from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
    from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415

    # Find the connectivity matrix file
    if not matrix_config.exists():
        msg = f"Connectivity matrix config file '{matrix_config}' not found!"
        raise OBIONEError(msg)
    with matrix_config.open(encoding="utf-8") as f:
        config_dict = json.load(f)
    edge_pop_config = config_dict.get(edge_population, {})
    matrix_file = matrix_config.parent / edge_pop_config.get("single", {}).get("path", "")
    if not matrix_file.is_file():
        msg = f"Connectivity matrix file '{matrix_file}' not found!"
        raise OBIONEError(msg)

    # Set up basic connectivity plots
    matrix_path = NamedPath(
        name=circuit_path.parent.name + "__BASIC_PLOTS__",  # Used as output name
        path=str(matrix_file),
    )
    cmat = ConnectivityMatrix.from_h5(matrix_path.path)
    if cmat.vertices.shape[0] <= _MAX_SMALL_MICROCIRCUIT_SIZE:
        plot_types = (
            "nodes",
            "small_adj_and_stats",
            "network_in_2D",
            "network_in_2D_circular",
            "property_table_extra",
        )
    else:
        plot_types = ("nodes", "connectivity_global", "connectivity_pathway")
    plots_init = BasicConnectivityPlotsScanConfig.Initialize(
        matrix_path=[matrix_path],
        plot_formats=("png",),
        rendering_cmap="tab10",
        plot_types=plot_types,
    )
    plots_config = BasicConnectivityPlotsScanConfig(initialize=plots_init)

    # Run basic connectivity plots
    grid_scan = GridScanGenerationTask(
        form=plots_config,
        output_root=circuit_path.parents[1],
        coordinate_directory_option="VALUE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    # Check and return output directory
    output_file_map = {
        "nodes": "node_stats.png",
        "small_adj_and_stats": "small_adj_and_stats.png",
        "network_in_2D": "small_network_in_2D.png",
        "network_in_2D_circular": "small_network_in_2D_circular.png",
        "property_table_extra": "property_table_extra.png",
        "connectivity_global": "network_global_stats.png",
        "connectivity_pathway": "network_pathway_stats.png",
    }
    output_dir = grid_scan.single_configs[0].coordinate_output_root
    output_files = [output_file_map[_pt] for _pt in plot_types]
    for file in output_files:
        if not (output_dir / file).is_file():
            msg = f"Connectivity plot '{file}' missing!"
            raise OBIONEError(msg)
    L.info(f"Basic connectivity plots generated in {output_dir}: {output_files}")
    return output_dir, output_files

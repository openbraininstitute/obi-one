"""Circuit-related utility functions."""

import json
import logging
import os
import shutil
from pathlib import Path

import bluepysnap as snap
import bluepysnap.circuit_validation
import h5py
import numpy as np
from bluepysnap import BluepySnapError
from entitysdk import types

from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.library.constants import _MAX_SMALL_MICROCIRCUIT_SIZE, _NEURON_PAIR_SIZE
from obi_one.utils.filesystem import filter_extension

L = logging.getLogger(__name__)


def fix_node_sets_file(circuit_path: Path) -> None:
    """Fixes the node sets file in case references are broken.

    This could happen in compound expressions which are pointing
    to non-existing node sets after circuit extraction.
    """

    def _find_broken_neuron_sets(nset_dict: dict) -> list:
        """Finds compound neuron sets with broken references."""
        broken_nsets = []
        for nset_name, nset_def in nset_dict.items():
            if isinstance(nset_def, list):  # Compound expression
                for n in nset_def:
                    if n not in nset_dict:
                        broken_nsets.append(nset_name)
                        break
        return broken_nsets

    def _remove_broken_neuron_sets(nset_dict: dict) -> None:
        """Removes neuron sets with broken references (in-place)."""
        broken_nsets = _find_broken_neuron_sets(nset_dict)
        if len(broken_nsets) > 0:
            # Remove all broken neuron sets from dict
            for nset in broken_nsets:
                del nset_dict[nset]
                L.warning(f"Node set '{nset}' broken and removed from node sets file.")
            # Recursively check again, since removal could cause
            # more broken neuron sets
            _remove_broken_neuron_sets(nset_dict)

    # Load node sets file
    c = snap.Circuit(circuit_path)
    with Path(c.config["node_sets_file"]).open(encoding="utf-8") as f:
        nset_dict = json.load(f)

    # Check if broken neuron sets
    broken_nsets = _find_broken_neuron_sets(nset_dict)
    if len(broken_nsets) == 0:
        # Nothing to fix
        return

    # Remove broken neuron sets, if any
    _remove_broken_neuron_sets(nset_dict)

    # Write new node sets file
    with Path(c.config["node_sets_file"]).open("w", encoding="utf-8") as f:
        json.dump(nset_dict, f, indent=2)


def get_circuit_size(c: Circuit) -> tuple[str, int, int, int]:
    """Returns the circuit scale, number of neurons, synapses, and connections."""
    c_sonata = c.sonata_circuit
    num_nrn = c_sonata.nodes[c.default_population_name].size
    if num_nrn == 1:
        scale = types.CircuitScale.single
    elif num_nrn == _NEURON_PAIR_SIZE:
        scale = types.CircuitScale.pair
    elif num_nrn <= _MAX_SMALL_MICROCIRCUIT_SIZE:
        scale = types.CircuitScale.small
    else:
        scale = types.CircuitScale.microcircuit
    # TODO: Add support for other scales as well
    # https://github.com/openbraininstitute/obi-one/issues/463

    if scale == types.CircuitScale.single:
        # Special case: Include extrinsic synapses & connections
        edge_pops = Circuit.get_edge_population_names(c_sonata, incl_virtual=True)
        edge_pops = [
            e for e in edge_pops if c_sonata.edges[e].target.name == c.default_population_name
        ]
    else:
        # Default case: Only include intrinsic synapse & connections
        try:
            default_epop = c.default_edge_population_name
        except ValueError as e:
            default_epop = None
            L.warning(e)
            # TODO: May erroneously lead to 0 synapses
        edge_pops = [] if default_epop is None else [default_epop]

    num_syn = np.sum([c_sonata.edges[e].size for e in edge_pops]).astype(int)
    num_conn = np.sum(
        [
            len(
                list(
                    c_sonata.edges[e].iter_connections(
                        target={"population": c_sonata.edges[e].target.name}
                    )
                )
            )
            for e in edge_pops
        ]
    ).astype(int)

    return scale, num_nrn, num_syn, num_conn


def rebase_config(config_dict: dict, old_base: str, new_base: str) -> None:
    """Rebase paths in a circuit config dict from old_base to new_base (in-place)."""
    old_base = str(Path(old_base).resolve())
    for key, value in config_dict.items():
        if isinstance(value, str):
            if value == old_base:
                config_dict[key] = ""
            else:
                config_dict[key] = value.replace(old_base, new_base)
        elif isinstance(value, dict):
            rebase_config(value, old_base, new_base)
        elif isinstance(value, list):
            for v in value:
                rebase_config(v, old_base, new_base)


def copy_mod_files(circuit_path: str, output_root: str, mod_folder: str) -> None:
    """Copy mod files from circuit directory to output root."""
    mod_folder = "mod"
    source_dir = Path(os.path.split(circuit_path)[0]) / mod_folder
    if Path(source_dir).exists():
        L.info("Copying mod files")
        dest_dir = Path(output_root) / mod_folder
        shutil.copytree(source_dir, dest_dir)


def run_validation(circuit_path: str) -> None:
    """Run SONATA circuit validation."""
    errors = snap.circuit_validation.validate(circuit_path, skip_slow=True)
    if len(errors) > 0:
        msg = f"Circuit validation error(s) found: {errors}"
        raise ValueError(msg)
    L.info("No validation errors found!")


def get_morph_dirs(
    pop_name: str,
    pop: snap.nodes.NodePopulation,  # ty:ignore[possibly-missing-submodule]
    original_circuit: snap.Circuit,
) -> tuple[dict, dict]:
    """Returns source and destination morphology directories for a node population."""
    src_morph_dirs = {}
    dest_morph_dirs = {}
    for morph_ext in ["swc", "asc", "h5"]:
        try:
            morph_folder = original_circuit.nodes[pop_name].morph._get_morphology_base(  # noqa: SLF001
                morph_ext
            )
            # TODO: Should not use private function!! But required to get path
            #       even if h5 container.
        except BluepySnapError:
            # Morphology folder for given extension not defined in config
            continue

        if not Path(morph_folder).exists():
            # Morphology folder/container does not exist
            continue

        if (
            Path(morph_folder).is_dir()
            and len(filter_extension(Path(morph_folder).iterdir(), morph_ext)) == 0  # ty:ignore[invalid-argument-type]
        ):
            # Morphology folder does not contain morphologies
            continue

        dest_morph_dirs[morph_ext] = pop.morph._get_morphology_base(morph_ext)  # noqa: SLF001
        # TODO: Should not use private function!!
        src_morph_dirs[morph_ext] = morph_folder
    return src_morph_dirs, dest_morph_dirs


def copy_morphologies(
    pop_name: str,
    pop: snap.nodes.NodePopulation,  # ty:ignore[possibly-missing-submodule]
    original_circuit: snap.Circuit,
) -> None:
    """Copy morphologies for a node population from original to extracted circuit."""
    L.info(f"Copying morphologies for population '{pop_name}' ({pop.size})")
    morphology_list = pop.get(properties="morphology").unique()

    src_morph_dirs, dest_morph_dirs = get_morph_dirs(pop_name, pop, original_circuit)

    if len(src_morph_dirs) == 0:
        msg = "ERROR: No morphologies of any supported format found!"
        raise ValueError(msg)
    for morph_ext, src_dir in src_morph_dirs.items():
        if morph_ext == "h5" and Path(src_dir).is_file():
            # TODO: If there is only one neuron extracted, consider removing
            #       the container
            # https://github.com/openbraininstitute/obi-one/issues/387

            # Copy containerized morphologies into new container
            L.info(f"Copying {len(morphology_list)} containerized .{morph_ext} morphologies")
            Path(os.path.split(dest_morph_dirs[morph_ext])[0]).mkdir(parents=True, exist_ok=True)
            src_container = src_dir
            dest_container = dest_morph_dirs[morph_ext]
            with (
                h5py.File(src_container) as f_src,
                h5py.File(dest_container, "a") as f_dest,
            ):
                skip_counter = 0
                for morphology_name in morphology_list:
                    if morphology_name in f_dest:
                        skip_counter += 1
                    else:
                        f_src.copy(
                            f_src[morphology_name],
                            f_dest,
                            name=morphology_name,
                        )
            L.info(
                f"Copied {len(morphology_list) - skip_counter} morphologies into"
                f" container ({skip_counter} already existed)"
            )
        else:
            # Copy morphology files
            L.info(f"Copying {len(morphology_list)} .{morph_ext} morphologies")
            Path(dest_morph_dirs[morph_ext]).mkdir(parents=True, exist_ok=True)
            for morphology_name in morphology_list:
                src_file = Path(src_dir) / f"{morphology_name}.{morph_ext}"
                dest_file = Path(dest_morph_dirs[morph_ext]) / f"{morphology_name}.{morph_ext}"
                if not Path(src_file).exists():
                    msg = f"ERROR: Morphology '{src_file}' missing!"
                    raise ValueError(msg)
                if not Path(dest_file).exists():
                    # Copy only, if not yet existing (could happen for shared
                    # morphologies among populations)
                    shutil.copyfile(src_file, dest_file)


def copy_hoc_files(
    pop_name: str,
    pop: snap.nodes.NodePopulation,  # ty:ignore[possibly-missing-submodule]
    original_circuit: snap.Circuit,
) -> None:
    """Copy biophysical neuron model (.hoc) files for a node population."""
    hoc_file_list = [
        hoc.split(":")[-1] + ".hoc" for hoc in pop.get(properties="model_template").unique()
    ]
    L.info(
        f"Copying {len(hoc_file_list)} biophysical neuron models (.hoc) for"
        f" population '{pop_name}' ({pop.size})"
    )

    source_dir = original_circuit.nodes[pop_name].config["biophysical_neuron_models_dir"]
    dest_dir = pop.config["biophysical_neuron_models_dir"]
    Path(dest_dir).mkdir(parents=True, exist_ok=True)

    for hoc_file in hoc_file_list:
        src_file = Path(source_dir) / hoc_file
        dest_file = Path(dest_dir) / hoc_file
        if not Path(src_file).exists():
            msg = f"ERROR: HOC file '{src_file}' missing!"
            raise ValueError(msg)
        if not Path(dest_file).exists():
            # Copy only, if not yet existing (could happen for shared hoc files
            # among populations)
            shutil.copyfile(src_file, dest_file)


def get_circuit_properties(c: Circuit) -> tuple[bool, bool, bool, bool]:
    """Returns circuit properties derived from the circuit files.

    Args:
        c: A Circuit object pointing to a valid SONATA circuit.

    Returns:
        Tuple of (has_morphologies, has_point_neurons, has_electrical_cell_models, has_spines).
    """
    # TODO: Implement actual detection logic based on circuit contents
    raise NotImplementedError("get_circuit_properties() is not yet implemented")


def generate_overview_figure(basic_plots_dir: Path | None, output_file: Path) -> Path:
    """Generate an overview figure of the circuit.

    Uses the circular 2D network plot if available, otherwise falls back to a template.
    """
    from importlib.resources import files  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    from obi_one.core.exception import OBIONEError  # noqa: PLC0415

    # Use circular view from basic connectivity plots, if existing
    if basic_plots_dir:
        fig_paths = basic_plots_dir / "small_network_in_2D_circular.png"
        if fig_paths.is_file():
            # Add table path (optional)
            tab_path = basic_plots_dir / "property_table_extra.png"
            if tab_path.is_file():
                fig_paths = (fig_paths, tab_path)
        else:
            fig_paths = None
    else:
        fig_paths = None

    # Use template figure from library if no circular plot available
    if fig_paths is None:
        fig_paths = Path(
            str(files("obi_one.scientific.library").joinpath("circuit_template.png"))
        )

    # Check that output file does not exist yet
    if output_file.exists():
        msg = f"Output file '{output_file}' already exists!"
        raise OBIONEError(msg)

    # Save output figure
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(fig_paths, tuple):
        # Stack images horizontally
        img_left = Image.open(fig_paths[0])
        img_right = Image.open(fig_paths[-1])
        width = img_left.width + img_right.width
        height = max(img_left.height, img_right.height)
        img_merged = Image.new("RGB", (width, height), (255, 255, 255))
        img_merged.paste(img_left, (0, 0))
        img_merged.paste(img_right, (img_left.width, height - img_right.height >> 1))
        img_merged.save(output_file)
    else:
        # Check that output file has the correct extension
        if output_file.suffix != fig_paths.suffix:
            msg = (
                f"Output file extension '{output_file.suffix}' does not match "
                f"figure extension '{fig_paths.suffix}'!"
            )
            raise OBIONEError(msg)

        # Copy figure to output file
        shutil.copy(fig_paths, output_file)

    return output_file


def run_circuit_folder_compression(circuit_path: Path, circuit_name: str, output_root: Path) -> Path:
    """Set up and run folder compression task.

    Args:
        circuit_path: Path to the circuit_config.json file.
        circuit_name: Name for the compressed archive.
        output_root: Directory where the compressed output will be written.

    Returns:
        Path to the generated .gz file.
    """
    from obi_one.core.exception import OBIONEError  # noqa: PLC0415
    from obi_one.core.path import NamedPath  # noqa: PLC0415
    from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
    from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415
    from obi_one.scientific.tasks.folder_compression import FolderCompressionScanConfig  # noqa: PLC0415

    folder_path = NamedPath(
        name="circuit_folder",
        path=str(circuit_path.parent),
    )
    compression_init = FolderCompressionScanConfig.Initialize(
        folder_path=folder_path,
        file_format="gz",
        file_name="circuit",
        archive_name=circuit_name,
    )
    folder_compressions_config = FolderCompressionScanConfig(initialize=compression_init)

    grid_scan = GridScanGenerationTask(
        form=folder_compressions_config,
        output_root=output_root,
        coordinate_directory_option="NONE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    output_file = (
        grid_scan.single_configs[0].coordinate_output_root
        / f"{compression_init.file_name}.{compression_init.file_format}"
    )
    if not output_file.exists():
        msg = "Compressed circuit file does not exist!"
        raise OBIONEError(msg)
    L.info(f"Circuit folder compressed into {output_file}")
    return output_file


def run_connectivity_matrix_extraction(circuit_path: Path, output_root: Path) -> tuple[Path, Path, str]:
    """Set up and run connectivity matrix extraction task.

    Args:
        circuit_path: Path to the circuit_config.json file.
        output_root: Directory where the matrix output will be written.

    Returns:
        Tuple of (output_dir, matrix_config_path, edge_population_name).
    """
    from obi_one.core.exception import OBIONEError  # noqa: PLC0415
    from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
    from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415
    from obi_one.scientific.tasks.connectivity_matrix_extraction import (  # noqa: PLC0415
        ConnectivityMatrixExtractionScanConfig,
    )

    circuit = Circuit(
        name="circuit",
        path=str(circuit_path),
    )
    edge_population = circuit.default_edge_population_name
    matrix_init = ConnectivityMatrixExtractionScanConfig.Initialize(
        circuit=circuit,
        edge_population=edge_population,
        node_attributes=("synapse_class", "layer", "mtype", "etype", "x", "y", "z"),
        with_matrix_config=True,
    )
    matrix_extraction_config = ConnectivityMatrixExtractionScanConfig(initialize=matrix_init)

    grid_scan = GridScanGenerationTask(
        form=matrix_extraction_config,
        output_root=output_root,
        coordinate_directory_option="NONE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    output_dir = grid_scan.single_configs[0].coordinate_output_root
    output_file = output_dir / "matrix_config.json"
    if not output_file.exists():
        msg = "Connectivity matrix config file does not exist!"
        raise OBIONEError(msg)
    L.info(f"Connectivity matrix extracted to {output_dir}")
    return output_dir, output_file, edge_population


def run_basic_connectivity_plots(
    matrix_config: Path, edge_population: str, output_root: Path
) -> tuple[Path, list]:
    """Set up and run basic connectivity plotting task.

    Args:
        matrix_config: Path to the matrix_config.json file.
        edge_population: Name of the edge population.
        output_root: Directory where the plot output will be written.

    Returns:
        Tuple of (output_dir, list of plot filenames).
    """
    from conntility import ConnectivityMatrix  # noqa: PLC0415

    from obi_one.core.exception import OBIONEError  # noqa: PLC0415
    from obi_one.core.path import NamedPath  # noqa: PLC0415
    from obi_one.core.run_tasks import run_tasks_for_generated_scan  # noqa: PLC0415
    from obi_one.core.scan_generation import GridScanGenerationTask  # noqa: PLC0415
    from obi_one.scientific.library.constants import _MAX_SMALL_MICROCIRCUIT_SIZE  # noqa: PLC0415
    from obi_one.scientific.tasks.basic_connectivity_plots import (  # noqa: PLC0415
        BasicConnectivityPlotsScanConfig,
    )

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

    matrix_path = NamedPath(
        name="connectivity_matrix",
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
        matrix_path=matrix_path,
        plot_formats=("png",),
        rendering_cmap="tab10",
        plot_types=plot_types,
    )
    plots_config = BasicConnectivityPlotsScanConfig(initialize=plots_init)

    grid_scan = GridScanGenerationTask(
        form=plots_config,
        output_root=output_root,
        coordinate_directory_option="NONE",
    )
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

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
    output_files = [output_file_map[pt] for pt in plot_types]
    for file in output_files:
        if not (output_dir / file).is_file():
            msg = f"Connectivity plot '{file}' missing!"
            raise OBIONEError(msg)
    L.info(f"Basic connectivity plots generated in {output_dir}: {output_files}")
    return output_dir, output_files

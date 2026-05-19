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

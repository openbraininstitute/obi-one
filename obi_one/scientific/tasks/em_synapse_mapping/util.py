"""Utilities for the EM synapse mapping task."""

import logging
from pathlib import Path

import h5py
from morph_spines.utils.morph_spine_merger import merge_morphologies_with_spines

L = logging.getLogger(__name__)


def merge_spiny_morphologies(
    source_files_with_neuron_names: list[tuple[Path, str]],
    output_path: Path,
    *,
    include_meshes: bool = True,
) -> None:
    """Merge multiple morphology-with-spines HDF5 files into one, renaming each neuron.

    Each source file must contain exactly one morphology. The single morphology
    in each file is renamed to the corresponding destination name.
    Spine libraries that share the neuron's name are renamed accordingly;
    shared spine libraries with different names are kept as-is.

    This is a convenience wrapper around morph_spines' merge_morphologies_with_spines
    for the common case where each source file has a single morphology and should be
    renamed to a known identifier.

    Args:
        source_files_with_neuron_names: list of (source_file_path, destination_name)
            pairs. Each source file must contain exactly one morphology, which will
            be renamed to the given destination name in the output.
        output_path: path to write the combined HDF5 file. Must not already exist.
        include_meshes: if True (default), include soma and spine mesh datasets.
            Otherwise, skip mesh datasets for a smaller file size.

    Raises:
        ValueError: If any source file does not contain exactly one morphology.
    """
    # Build rename_map by resolving the single morphology name in each file
    source_files: list[Path] = []
    rename_map: dict[tuple[Path, str], str] = {}

    for path, dest_name in source_files_with_neuron_names:
        src_path = Path(path)
        source_files.append(src_path)

        with h5py.File(src_path, "r") as h5:
            if "morphology" not in h5:
                err_str = f"No /morphology group found in {src_path}"
                raise ValueError(err_str)
            morph_keys = list(h5["morphology"].keys())
            if len(morph_keys) != 1:
                err_str = (
                    f"Expected exactly 1 morphology in {src_path}, "
                    f"found {len(morph_keys)}: {morph_keys}"
                )
                raise ValueError(err_str)
            original_name = morph_keys[0]

        rename_map[src_path, original_name] = dest_name

    merge_morphologies_with_spines(
        source_files=source_files,
        output_path=output_path,
        rename_map=rename_map,
        include_meshes=include_meshes,
    )

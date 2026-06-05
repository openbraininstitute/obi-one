import logging
from pathlib import Path

import h5py

L = logging.getLogger(__name__)


def merge_spiny_morphologies(
    source_files: list[Path],
    output_path: Path,
    *,
    include_meshes: bool = True,
) -> None:
    """Merge multiple morphology-with-spines HDF5 files into one.

    Supports merging files with already multiple morphologies-with-spines in them.
    All morphologies and spines are copied into the output file, keeping their original keys.
    Raises ValueError in case of duplicated keys between source files.

    Args:
        source_files: list of morphology-with-spines HDF5 files to merge.
        output_path: path to write the combined HDF5 file. For simplicity, must be a new file.
        include_meshes: if True (default), include soma and spine mesh datasets.
            Otherwise, skip mesh datasets for a smaller file size.
    """
    neuron_keyed_groups = ["edges", "morphology"]
    if include_meshes:
        neuron_keyed_groups.append("soma/meshes")
    spine_library_groups = ["spines/skeletons"]
    if include_meshes:
        spine_library_groups.append("spines/meshes")

    with h5py.File(output_path, "w") as h5_out:
        for src_path in source_files:
            with h5py.File(src_path, "r") as h5_in:
                _merge_one_source(
                    h5_in, h5_out, src_path, neuron_keyed_groups, spine_library_groups
                )


def _merge_one_source(
    h5_in: h5py.File,
    h5_out: h5py.File,
    src_path: Path,
    neuron_keyed_groups: list[str],
    spine_library_groups: list[str],
) -> None:
    """Merge all morphologies from one source file into the output."""
    if "morphology" not in h5_in:
        err_str = f"No /morphology group found in {src_path}"
        raise ValueError(err_str)

    src_names = list(h5_in["morphology"].keys())

    for morph_key in src_names:
        _copy_neuron_groups(h5_in, h5_out, morph_key, src_path, neuron_keyed_groups)

    for grp_path in spine_library_groups:
        src_grp = _navigate_h5_path(h5_in, grp_path)
        if src_grp is None:
            continue
        dst_parent = h5_out.require_group(grp_path)
        for spine_key in src_grp:
            if spine_key in dst_parent:
                err_str = (
                    f"Duplicate spine key '{spine_key}' in "
                    f"output group '{grp_path}' (from {src_path})"
                )
                raise ValueError(err_str)
            h5_in.copy(src_grp[spine_key], dst_parent, name=spine_key)


def _copy_neuron_groups(
    h5_in: h5py.File,
    h5_out: h5py.File,
    morph_key: str,
    src_path: Path,
    neuron_keyed_groups: list[str],
) -> None:
    """Copy neuron-keyed groups for one morphology key, raising on duplicates."""
    for grp_path in neuron_keyed_groups:
        src_grp = _navigate_h5_path(h5_in, grp_path)
        if src_grp is None or morph_key not in src_grp:
            continue
        dst_parent = h5_out.require_group(grp_path)
        if morph_key in dst_parent:
            err_str = (
                f"Duplicate morphology key '{morph_key}' in "
                f"output group '{grp_path}' (from {src_path})"
            )
            raise ValueError(err_str)
        h5_in.copy(src_grp[morph_key], dst_parent, name=morph_key)
        if grp_path == "edges":
            metadata_path = f"{grp_path}/{morph_key}/metadata"
            if metadata_path in h5_in:
                dst_grp = dst_parent[morph_key]
                if "metadata" not in dst_grp:
                    h5_in.copy(h5_in[metadata_path], dst_grp, name="metadata")


def _navigate_h5_path(h5: h5py.File, path: str) -> h5py.Group | None:
    """Navigate an HDF5 file to a nested group path, returning None if not found."""
    grp = h5
    for part in path.split("/"):
        if part in grp:
            grp = grp[part]
        else:
            return None
    return grp

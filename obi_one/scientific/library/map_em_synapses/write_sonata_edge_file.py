"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.library.map_em_synapses.write_sonata_edge_file import (
    adjust_edge_index_groups,
    create_or_resize_dataset,
    H5Group,
    h5py,
    libsonata,
    numpy,
    os,
    pandas,
    Path,
    write_edges,
)

from obi_one_lazy.scientific.library.map_em_synapses.write_sonata_edge_file import (
    _STR_POST_NODE,
    _STR_PRE_NODE,
    _write_indexes,
)

__all__ = [
    "adjust_edge_index_groups",
    "create_or_resize_dataset",
    "H5Group",
    "h5py",
    "libsonata",
    "numpy",
    "os",
    "pandas",
    "Path",
    "write_edges",
    "_STR_POST_NODE",
    "_STR_PRE_NODE",
    "_write_indexes",
]

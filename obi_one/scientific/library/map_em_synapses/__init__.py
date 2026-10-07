"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.library.map_em_synapses import (
    map_afferents_to_spiny_morphology,
    map_synapse_locations,
    write_edges,
    write_nodes,
    write_sonata_edge_file,
    write_sonata_nodes_file,
)

__all__ = [
    "map_afferents_to_spiny_morphology",
    "map_synapse_locations",
    "write_edges",
    "write_nodes",
    "write_sonata_edge_file",
    "write_sonata_nodes_file",
]

"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.scientific.library.map_em_synapses._defaults import (
    Client,
    deepcopy,
    default_node_spec_for,
    DEFAULT_NODE_SPECS,
    EMDataSetFromID,
    sonata_config_for,
    SYNAPTOME_SONATA_CONFIG,
)

__all__ = [
    "Client",
    "deepcopy",
    "default_node_spec_for",
    "DEFAULT_NODE_SPECS",
    "EMDataSetFromID",
    "sonata_config_for",
    "SYNAPTOME_SONATA_CONFIG",
]

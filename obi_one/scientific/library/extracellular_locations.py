"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports, import-private-name]

from obi_one_lazy.scientific.library.extracellular_locations import (
    Any,
    dataclass,
    extracellular_locations_block_dictionary_summary,
    extracellular_locations_block_summary,
    ExtracellularLocationsUnion,
    Figure,
    np,
    plot_extracellular_arrays,
    plt,
    snap,
)

from obi_one_lazy.scientific.library.extracellular_locations import (
    _ArrayPlot,
    _MEDIUM_CIRCUIT,
    _SMALL_CIRCUIT,
    _soma_marker_style,
    _TICK_TOL,
    _ZERO_TOL,
)

__all__ = [
    "Any",
    "dataclass",
    "extracellular_locations_block_dictionary_summary",
    "extracellular_locations_block_summary",
    "ExtracellularLocationsUnion",
    "Figure",
    "np",
    "plot_extracellular_arrays",
    "plt",
    "snap",
    "_ArrayPlot",
    "_MEDIUM_CIRCUIT",
    "_SMALL_CIRCUIT",
    "_soma_marker_style",
    "_TICK_TOL",
    "_ZERO_TOL",
]

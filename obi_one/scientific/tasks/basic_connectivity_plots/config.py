"""Basic connectivity plots task configuration."""

from pathlib import Path
from typing import ClassVar, Self

import matplotlib.pyplot as plt
from pydantic import model_validator

from obi_one.core.block import Block
from obi_one.core.path import NamedPath
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin

DPI = 300


class BasicConnectivityPlotsScanConfig(ScanConfig):
    """Class to generate basic connectivity plots and stats from a ConnectivityMatrix object.

    Supported plot types:
      - "nodes": Node statistics (e.g., synapse class, layer, mtype).
      - "connectivity_pathway": Connection probabilities per pathway/grouping.
                                Not useful for small circuits.
      - "connectivity_global": Global connection probabilities across the network.
                                Not useful for small circuits
      - "small_adj_and_stats": Matrix and node statistics for small connectomes only (<= 20 nodes).
      - "network_in_2D": 2D visualization of the network for small connectomes only (<= 20 nodes).
      - "network_in_2D_circular": Circular projection only for small connectomes (<= 20 nodes).
      - "property_table": Table of node properties for small connectomes only (<= 20 nodes).
      - "property_table_extra": Extended property table with synapse class column (but no
        color legend) for small connectomes (<= 20 nodes).
    """

    name: ClassVar[str] = "Basic Connectivity Plots"
    description: ClassVar[str] = (
        "Generates basic connectivity plots and stats from a ConnectivityMatrix object."
    )

    class Initialize(Block):
        matrix_path: NamedPath | list[NamedPath]
        # TODO: implement node population option
        plot_formats: tuple[str, ...] = ("png", "pdf", "svg")
        plot_types: tuple[str, ...] = (
            "nodes",  # for any connectivity matrix
            "connectivity_global",
            "connectivity_pathway",  # for medium and large connectomes
            "small_adj_and_stats",
            "network_in_2D",
            "network_in_2D_circular",
            "property_table",  # for small connectomes only
        )
        rendering_cmap: str | None = None  # Color map of the node identities
        rendering_color_file: str | None = None  # Color map file of the nod identities
        dpi: int = DPI

        @model_validator(mode="after")
        def check_rendering_colors_for_property_table(self) -> Self:
            if "property_table" in self.plot_types:
                if self.rendering_cmap == "custom":
                    if not Path(self.rendering_color_file).is_file():  # ty:ignore[invalid-argument-type]
                        msg = "The rendering_color_file is not an existing file."
                        raise ValueError(msg)
                elif self.rendering_cmap is not None:
                    cmap = plt.get_cmap(self.rendering_cmap)
                    if not hasattr(cmap, "colors"):
                        msg = "You need to use a discrete color map"
                        raise ValueError(msg)
                else:
                    msg = (
                        "When plotting `property_table` either a discrete colormap "
                        "or a color map file must be passed."
                    )
                    raise ValueError(msg)

            return self

    initialize: Initialize


class BasicConnectivityPlotsSingleConfig(BasicConnectivityPlotsScanConfig, SingleConfigMixin):
    """Generates and saves basic connectivity plots from a ConnectivityMatrix objects."""

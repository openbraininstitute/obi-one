import contextlib
import logging
from pathlib import Path
from typing import ClassVar, Self

import entitysdk.client
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from conntility import ConnectivityMatrix
from pydantic import model_validator

from obi_one.core.block import Block
from obi_one.core.path import NamedPath
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.basic_connectivity_plots_helpers import (
    compute_global_connectivity,
    connection_probability_pathway,
    connection_probability_within_pathway,
    plot_connection_probability_pathway_stats,
    plot_connection_probability_stats,
    plot_node_stats,
    plot_node_table,
    plot_smallMC,
    plot_smallMC_network_stats,
)

with contextlib.suppress(ImportError):  # Try to import connalysis
    from connalysis.network.topology import node_degree
    from connalysis.randomization import ER_model

L = logging.getLogger(__name__)


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
      - "property_table": Table of node properties for small connectomes only (<= 20 nodes).
    """

    single_coord_class_name: ClassVar[str] = "BasicConnectivityPlotsSingleConfig"
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
            "property_table",  # for small connectomes only
        )
        rendering_cmap: str | None = None  # Color map of the node identities
        rendering_color_file: str | None = None  # Color map file of the nod identities
        dpi: int = 300

        @model_validator(mode="after")
        def check_rendering_colors_for_property_table(self) -> Self:
            if "property_table" in self.plot_types:
                if self.rendering_cmap == "custom":
                    if not Path(self.rendering_color_file).is_file():
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


class BasicConnectivityPlotsTask(Task):
    """Task to generate and save basic connectivity plots from a ConnectivityMatrix object."""

    config: BasicConnectivityPlotsSingleConfig

    @staticmethod
    def nodes_plot(
        conn: ConnectivityMatrix,
        full_width: int,
        plot_formats: tuple[str, ...],
        dpi: int,
        dir_path: str | Path,
    ) -> None:
        node_cmaps = {
            "synapse_class": mcolors.LinearSegmentedColormap.from_list("RedBlue", ["C0", "C3"]),
            "layer": plt.get_cmap("Dark2"),
            "mtype": plt.get_cmap("GnBu"),
        }
        fig = plot_node_stats(conn, node_cmaps, full_width)
        for fmt in plot_formats:
            output_file = Path(dir_path) / f"node_stats.{fmt}"
            fig.savefig(output_file, dpi=dpi, bbox_inches="tight")

    @staticmethod
    def connectivity_pathway_plot(
        full_width: int,
        plot_formats: tuple[str, ...],
        dpi: int,
        size: tuple[int, int],
        n_min_stats: int,
        conn: ConnectivityMatrix,
        deg: dict[str, float],
        deg_er: dict[str, float],
        dir_path: str | Path,
    ) -> None:
        if size[0] < n_min_stats:
            L.warning("Your network is likely too small for these plots to be informative.")
        conn_probs = {"full": {}, "within": {}}
        for grouping_prop in ["synapse_class", "layer", "mtype"]:
            conn_probs["full"][grouping_prop] = connection_probability_pathway(conn, grouping_prop)
            conn_probs["within"][grouping_prop] = connection_probability_within_pathway(
                conn, grouping_prop, max_dist=100
            )
        # Plot network metrics
        fig_network_pathway = plot_connection_probability_pathway_stats(
            full_width, conn_probs, deg, deg_er
        )
        for fmt in plot_formats:
            output_file = Path(dir_path) / f"network_pathway_stats.{fmt}"
            fig_network_pathway.savefig(output_file, dpi=dpi, bbox_inches="tight")

    @staticmethod
    def connectivity_global_plot(
        full_width: int,
        plot_formats: tuple[str, ...],
        dpi: int,
        size: tuple[int, int],
        n_min_stats: int,
        adj: np.ndarray,
        adj_er: np.ndarray,
        conn: ConnectivityMatrix,
        dir_path: str | Path,
    ) -> None:
        if size[0] < n_min_stats:
            L.warning("Your network is likely too small for these plots to be informative.")
        # Global connection probabilities
        global_conn_probs = {"full": None, "within": None}
        global_conn_probs["full"] = compute_global_connectivity(adj, adj_er, connection_type="full")
        global_conn_probs["widthin"] = compute_global_connectivity(
            adj, adj_er, v=conn.vertices, connection_type="within", max_dist=100, cols=["x", "y"]
        )

        # Plot network metrics
        fig_network_global = plot_connection_probability_stats(full_width, global_conn_probs)
        for fmt in plot_formats:
            output_file = Path(dir_path) / f"network_global_stats.{fmt}"
            fig_network_global.savefig(output_file, dpi=dpi, bbox_inches="tight")

    @staticmethod
    def small_adj_and_stats_plot(
        full_width: int,
        plot_formats: tuple[str, ...],
        dpi: int,
        size: tuple[int, int],
        n_max_2d_plot: int,
        conn: ConnectivityMatrix,
        dir_path: str | Path,
    ) -> None:
        if size[0] > n_max_2d_plot:
            L.warning("Your network is too large for these plots.")
        else:
            fig_adj_and_stats = plot_smallMC_network_stats(
                conn,
                full_width,
                color_indeg=plt.get_cmap("Set2")(0),
                color_outdeg=plt.get_cmap("Set2")(2),
                color_strength=plt.get_cmap("Set2")(1),
                cmap_adj=plt.get_cmap("viridis"),
            )

            for fmt in plot_formats:
                output_file = Path(dir_path) / f"small_adj_and_stats.{fmt}"
                fig_adj_and_stats.savefig(output_file, dpi=dpi, bbox_inches="tight")

    @staticmethod
    def network_in_2D_plot(
        full_width: int,
        plot_formats: tuple[str, ...],
        dpi: int,
        size: tuple[int, int],
        n_max_2d_plot: int,
        conn: ConnectivityMatrix,
        dir_path: str | Path,
    ) -> None:
        if size[0] > n_max_2d_plot:
            L.warning("Your network is too large for these plots.")
        else:
            cmap = mcolors.LinearSegmentedColormap.from_list("RedBlue", ["C0", "C3"])
            fig_network_in_2d = plot_smallMC(conn, cmap, full_width, textsize=14)

            for fmt in plot_formats:
                output_file = Path(dir_path) / f"small_network_in_2D.{fmt}"
                fig_network_in_2d.savefig(output_file, dpi=dpi, bbox_inches="tight")

    @staticmethod
    def property_table_plot(
        plot_formats: tuple[str, ...],
        dpi: int,
        size: tuple[int, int],
        n_max_2d_plot: int,
        conn: ConnectivityMatrix,
        dir_path: str | Path,
        colors_cmap: mcolors.Colormap,
        colors_file: str | Path,
        figsize: tuple[float, float] = (5, 2),
    ) -> None:
        if size[0] > n_max_2d_plot:
            L.warning("Your network is too large for this table.")
        else:
            fig_property_table = plot_node_table(
                conn,
                figsize=figsize,
                colors_cmap=colors_cmap,
                colors_file=colors_file,
                h_scale=2.5,
                v_scale=2.5,
            )

            for fmt in plot_formats:
                output_file = Path(dir_path) / f"property_table.{fmt}"
                fig_property_table.savefig(output_file, dpi=dpi, bbox_inches="tight")

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
    ) -> None:
        if "node_degree" not in globals() or "ER_model" not in globals():
            msg = (
                "Import of 'node_degree' or 'ER_model' failed. You probably need to install"
                " connalysis locally."
            )
            raise ValueError(msg)

        # TODO: Maybe move width outside, but then fontsize would have to be changed accordingly
        full_width = 16
        # Set plot format, resolution and plot types
        plot_formats = self.config.initialize.plot_formats
        plot_types = self.config.initialize.plot_types
        dpi = self.config.initialize.dpi
        L.info(f"Plot Formats: {plot_formats}")
        L.info(f"Plot Types: {plot_types}")

        L.info(f"Info: Running idx {self.config.idx}, plots for {plot_types}")

        # Load matrix
        L.info(f"Info: Loading matrix '{self.config.initialize.matrix_path}'")
        conn = ConnectivityMatrix.from_h5(self.config.initialize.matrix_path.path)

        # Size metrics
        size = np.array([len(conn.vertices), conn.matrix.nnz, conn.matrix.sum()])
        L.info("Neuron, connection and synapse counts")
        L.info(size)
        output_file = Path(self.config.coordinate_output_root) / "size.npy"
        np.save(output_file, size)

        # Node metrics
        if "nodes" in plot_types:
            self.nodes_plot(conn, full_width, plot_formats, dpi, self.config.coordinate_output_root)

        # Degrees of matrix and control
        adj = conn.matrix.astype(bool)
        adj_er = ER_model(adj)
        deg = node_degree(adj, direction=("IN", "OUT"))
        deg_er = node_degree(adj_er, direction=("IN", "OUT"))

        n_min_stats = 50  # Minimum number of nodes for statistics
        n_max_2d_plot = 20  # Maximum number of nodes for 2D plots and table

        # Network metrics for large circuits
        # Connection probabilities per pathway
        if "connectivity_pathway" in plot_types:
            self.connectivity_pathway_plot(
                full_width,
                plot_formats,
                dpi,
                size,
                n_min_stats,
                conn,
                deg,
                deg_er,
                self.config.coordinate_output_root,
            )

        # Global connection probabilities
        if "connectivity_global" in plot_types:
            self.connectivity_global_plot(
                full_width,
                plot_formats,
                dpi,
                size,
                n_min_stats,
                adj,
                adj_er,
                conn,
                self.config.coordinate_output_root,
            )

        # Network metrics for small circuits
        # Plot the adjacency matrix, Nsyn and degrees
        if "small_adj_and_stats" in plot_types:
            self.small_adj_and_stats_plot(
                full_width,
                plot_formats,
                dpi,
                size,
                n_max_2d_plot,
                conn,
                self.config.coordinate_output_root,
            )

        # Plot network in 2D
        if "network_in_2D" in plot_types:
            self.network_in_2D_plot(
                full_width,
                plot_formats,
                dpi,
                size,
                n_max_2d_plot,
                conn,
                self.config.coordinate_output_root,
            )

        # Plot table of properties
        if "property_table" in plot_types:
            self.property_table_plot(
                plot_formats,
                dpi,
                size,
                n_max_2d_plot,
                conn,
                self.config.coordinate_output_root,
                colors_cmap=self.config.initialize.rendering_cmap,
                colors_file=self.config.initialize.rendering_color_file,
                figsize=(5, 2),
            )

        L.info(f"Done with {self.config.idx}")

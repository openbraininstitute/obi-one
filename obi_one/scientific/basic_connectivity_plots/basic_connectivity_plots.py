import logging
import os
import traceback
import warnings
from typing import ClassVar, Optional
from pydantic import model_validator


import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


L = logging.getLogger(__name__)

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateMixin
from obi_one.scientific.basic_connectivity_plots.helpers import (
    compute_global_connectivity,
    connection_probability_pathway,
    connection_probability_within_pathway,
    plot_connection_probability_pathway_stats,
    plot_connection_probability_stats,
    plot_node_stats,
    plot_smallMC_network_stats,
    plot_smallMC, 
    plot_node_table
)

import entitysdk.client

try:
    from connalysis.network.topology import node_degree
    from connalysis.randomization import ER_model
    from conntility import ConnectivityMatrix
except ImportError:
    warnings.warn("Connectome functionalities not available", UserWarning, stacklevel=1)


class BasicConnectivityPlots(Form):
    """Class to generate basic connectivity plots and stats from a ConnectivityMatrix object."""

    single_coord_class_name: ClassVar[str] = "BasicConnectivityPlot"
    name: ClassVar[str] = "Basic Connectivity Plots"
    description: ClassVar[str] = (
        "Generates basic connectivity plots and stats from a ConnectivityMatrix object."
    )

    class Initialize(Block):
        matrix_path: NamedPath | list[NamedPath]
        # TODO: implement node population option
        # node_population: None | str | list[None | str] = None
        plot_formats: tuple[str, ...] = ("png", "pdf", "svg")
        plot_types: tuple[str, ...] = ("nodes", # for any connectivity matrix
                                       "connectivity_global", "connectivity_pathway", # for medium and large connectomes
                                       "small_adj_and_stats", "network_in_2D", "property_table", # for small connectomes only
                                       )
        rendering_cmap: Optional[str] = None # Color map of the node identities
        rendering_color_file: Optional[str] = None # Color map file of the nod identities
        dpi: int = 300

        @model_validator(mode="after")
        def check_rendering_colors_for_property_table(self):
            if "property_table" in self.plot_types:
                if self.rendering_cmap == "custom":
                    if not Path(self.rendering_color_file).is_file():
                        raise ValueError(
                            "The rendering_color_file is not an existing file.")
                elif self.rendering_cmap is not None: 
                    cmap = plt.get_cmap(self.rendering_cmap)
                    if not hasattr(cmap, "colors"):
                        raise ValueError(f"You need to use a discrete color map")
                else: 
                    raise ValueError("When plotting `property_table` either a discrete colormap or a color map file must be passed.")
                
            return self

    initialize: Initialize


class BasicConnectivityPlot(BasicConnectivityPlots, SingleCoordinateMixin):
    """
    Generates and saves basic connectivity plots from a ConnectivityMatrix objects.

    Supported plot types:
      - "nodes": Node statistics (e.g., synapse class, layer, mtype).
      - "connectivity_pathway": Connection probabilities per pathway/grouping.  Not useful for small circuits.
      - "connectivity_global": Global connection probabilities across the network. Not useful for small circuits 
    - "small_adj_and_stats": Adjacency matrix and node statistics for small connectomes only (<= 20 nodes).
    - "network_in_2D": 2D visualization of the network for small connectomes only (<= 20 nodes).
    - "property_table": Table of node properties for small connectomes only (<= 20 nodes).

    Raises:
        Exception: If any error occurs during processing or plotting.
    """
    def run(self, db_client: entitysdk.client.Client = None) -> None:
        try:
            full_width = 16 #TODO: Maybe move this outside, but then fontsize would have to be changed accordingly
            # Set plot format, resolution and plot types
            plot_formats = self.initialize.plot_formats
            plot_types = self.initialize.plot_types
            dpi = self.initialize.dpi
            L.info(f"Plot Formats: {plot_formats}")
            L.info("Plot Types: {plot_types}")

            L.info(f"Info: Running idx {self.idx}, plots for {plot_types}")

            # Load matrix
            L.info(f"Info: Loading matrix '{self.initialize.matrix_path}'")
            conn = ConnectivityMatrix.from_h5(self.initialize.matrix_path.path)

            # Size metrics
            size = np.array([len(conn.vertices), conn.matrix.nnz, conn.matrix.sum()])
            L.info("Neuron, connection and synapse counts")
            L.info(size)
            output_file = os.path.join(self.coordinate_output_root, "size.npy")
            np.save(output_file, size)

            # Node metrics
            if "nodes" in plot_types:
                node_cmaps = {
                    "synapse_class": mcolors.LinearSegmentedColormap.from_list(
                        "RedBlue", ["C0", "C3"]
                    ),
                    "layer": plt.get_cmap("Dark2"),
                    "mtype": plt.get_cmap("GnBu"),
                }
                fig = plot_node_stats(conn, node_cmaps, full_width)
                for format in plot_formats:
                    output_file = os.path.join(self.coordinate_output_root, f"node_stats.{format}")
                    fig.savefig(output_file, dpi=dpi, bbox_inches="tight")

            # Degrees of matrix and control
            adj = conn.matrix.astype(bool)
            adj_ER = ER_model(adj)
            deg = node_degree(adj, direction=("IN", "OUT"))
            deg_ER = node_degree(adj_ER, direction=("IN", "OUT"))
            
            # Network metrics for large circuits
            # Connection probabilities per pathway
            if "connectivity_pathway" in plot_types:
                if size[0]<50: L.warning("Your network is likely too small for these plots to be informative.") 
                conn_probs = {"full": {}, "within": {}}
                for grouping_prop in ["synapse_class", "layer", "mtype"]:
                    conn_probs["full"][grouping_prop] = connection_probability_pathway(
                        conn, grouping_prop
                    )
                    conn_probs["within"][grouping_prop] = connection_probability_within_pathway(
                        conn, grouping_prop, max_dist=100
                    )
                # Plot network metrics
                fig_network_pathway = plot_connection_probability_pathway_stats(
                    full_width, conn_probs, deg, deg_ER
                )
                for format in plot_formats:
                    output_file = os.path.join(
                        self.coordinate_output_root, f"network_pathway_stats.{format}"
                    )
                    fig_network_pathway.savefig(output_file, dpi=dpi, bbox_inches="tight")

            # Global connection probabilities
            if "connectivity_global" in plot_types:
                if size[0]<50: L.warning("Your network is likely too small for these plots to be informative.") 
                # Global connection probabilities
                global_conn_probs = {"full": None, "within": None}
                global_conn_probs["full"] = compute_global_connectivity(adj, adj_ER, type="full")
                global_conn_probs["widthin"] = compute_global_connectivity(
                    adj, adj_ER, v=conn.vertices, type="within", max_dist=100, cols=["x", "y"]
                )

                # Plot network metrics
                fig_network_global = plot_connection_probability_stats(
                    full_width, global_conn_probs
                )
                for format in plot_formats:
                    output_file = os.path.join(
                        self.coordinate_output_root, f"network_global_stats.{format}"
                    )
                    fig_network_global.savefig(output_file, dpi=dpi, bbox_inches="tight")
            
            # Network metrics for small circuits
            # Plot the adjacency matrix, Nsyn and degrees
            if "small_adj_and_stats" in plot_types:
                if size[0]>20: 
                    L.warning("Your network is too large for these plots.") 
                else:
                    fig_adj_and_stats= plot_smallMC_network_stats(conn, full_width,
                                                                  color_indeg=plt.get_cmap("Set2")(0),
                                                                  color_outdeg=plt.get_cmap("Set2")(2),
                                                                  color_strength=plt.get_cmap("Set2")(1),
                                                                  cmap_adj=plt.get_cmap("viridis"))

                    for format in plot_formats:
                        output_file = os.path.join(
                            self.coordinate_output_root, f"small_adj_and_stats.{format}"
                        )
                        fig_adj_and_stats.savefig(output_file, dpi=dpi, bbox_inches="tight")

            # Plot network in 2D
            if "network_in_2D" in plot_types:
                if size[0]>20: 
                    L.warning("Your network is too large for these plots.") 
                else:
                    cmap = mcolors.LinearSegmentedColormap.from_list("RedBlue", ["C0", "C3"])
                    fig_network_in_2D= plot_smallMC(conn, cmap, full_width ,textsize=14)
                    
                    for format in plot_formats:
                        output_file = os.path.join(
                            self.coordinate_output_root, f"small_network_in_2D.{format}"
                        )
                        fig_network_in_2D.savefig(output_file, dpi=dpi, bbox_inches="tight")

            # Plot table of properties
            if "property_table" in plot_types:
                if size[0]>20: 
                    L.warning("Your network is too large for this table.") 
                else:
                    fig_property_table= plot_node_table(conn, figsize=(5,2), 
                    colors_cmap = self.initialize.rendering_cmap,
                    colors_file = self.initialize.rendering_color_file,
                    h_scale = 2.5, 
                    v_scale = 2.5
                    )
                    
                    for format in plot_formats:
                        output_file = os.path.join(
                            self.coordinate_output_root, f"property_table.{format}"
                        )
                        fig_property_table.savefig(output_file, dpi=dpi, bbox_inches="tight")

                    

            L.info(f"Done with {self.idx}")

        except Exception as e:
            traceback.print_exception(e)

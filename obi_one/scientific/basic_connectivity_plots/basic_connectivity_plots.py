import os
import traceback
import warnings

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np

from obi_one.scientific.basic_connectivity_plots.helpers import (
    compute_global_connectivity,
    connection_probability_pathway,
    connection_probability_within_pathway,
    plot_connection_probability_pathway_stats,
    plot_connection_probability_stats,
    plot_node_stats,
)
from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateMixin

from typing import ClassVar

try:
    from connalysis.network.topology import node_degree
    from connalysis.randomization import ER_model
    from conntility import ConnectivityMatrix
except ImportError:
    warnings.warn("Connectome functionalities not available", UserWarning, stacklevel=1)


class BasicConnectivityPlots(Form):
    """
    Class to generate basic connectivity plots and stats from a ConnectivityMatrix object.
    """

    single_coord_class_name: ClassVar[str] = "BasicConnectivityPlot"

    class Initialize(Block):
        matrix_path: NamedPath | list[NamedPath]
        # TODO: implement node population option
        # node_population: None | str | list[None | str] = None
        plot_formats:  tuple[str, ...] = ("png", "pdf", "svg")
        plot_types:  tuple[str, ...] = ("nodes", "connectivity_global", "connectivity_pathway")
        dpi: int = 300

    initialize: Initialize



class BasicConnectivityPlot(BasicConnectivityPlots, SingleCoordinateMixin):
    """
    """
    
    def run(self) -> None:

        try:

            # Set plot format, resolution and plot types
            plot_formats = self.initialize.plot_formats
            plot_types = self.initialize.plot_types
            dpi = self.initialize.dpi    
            print("Plot Formats:", plot_formats)
            print("Plot Types:", plot_types)

            print(f"Info: Running idx {self.idx}, plots for {plot_types}")

            # Load matrix
            print(f"Info: Loading matrix '{self.initialize.matrix_path}'")
            conn = ConnectivityMatrix.from_h5(self.initialize.matrix_path.path)

            # Size metrics 
            size = np.array([len(conn.vertices),
                             conn.matrix.nnz,
                             conn.matrix.sum()])
            print("Neuron, connection and synapse counts")
            print(size) 
            output_file = os.path.join(self.coordinate_output_root, f"size.npy")
            np.save(output_file, size)

            # Node metrics 
            if "nodes" in plot_types:   
                node_cmaps={"synapse_class":mcolors.LinearSegmentedColormap.from_list('RedBlue', ["C0", "C3"]), 
                            "layer":plt.get_cmap("Dark2"), 
                            "mtype": plt.get_cmap("GnBu")}
                fig=plot_node_stats(conn, node_cmaps)
                for format in plot_formats:
                    output_file = os.path.join(self.coordinate_output_root, f"node_stats.{format}")
                    fig.savefig(output_file, dpi=dpi,  bbox_inches='tight')


            ### Compute network metrics
            full_width=16 # width of the Figure TODO move out
            # Degrees of matrix and control 
            adj=conn.matrix.astype(bool)
            adj_ER=ER_model(adj)
            deg=node_degree(adj, direction=('IN', 'OUT'))
            deg_ER=node_degree(adj_ER, direction=('IN', 'OUT')) 
            # Connection probabilities per pathway
            if "connectivity_pathway" in plot_types:
                conn_probs={"full":{}, "within":{}}
                for grouping_prop in ["synapse_class", "layer", "mtype"]:
                    conn_probs["full"][grouping_prop]= connection_probability_pathway(conn, grouping_prop)
                    conn_probs["within"][grouping_prop]= connection_probability_within_pathway(conn, grouping_prop, max_dist=100)
                # Plot network metrics
                fig_network_pathway=plot_connection_probability_pathway_stats(full_width, conn_probs, deg, deg_ER)
                for format in plot_formats:
                    output_file = os.path.join(self.coordinate_output_root, f"network_pathway_stats.{format}")
                    fig_network_pathway.savefig(output_file, dpi=dpi,  bbox_inches='tight')


            # Global connection probabilities
            if "connectivity_global" in plot_types:
                # Global connection probabilities
                global_conn_probs={"full":None, "within":None}
                global_conn_probs["full"]= compute_global_connectivity(adj, adj_ER, type="full")
                global_conn_probs["widthin"]=compute_global_connectivity(adj, adj_ER, v=conn.vertices, type="within", max_dist=100, cols=["x", "y"])
            
                # Plot network metrics
                fig_network_global=plot_connection_probability_stats(full_width, global_conn_probs)
                for format in plot_formats:
                    output_file = os.path.join(self.coordinate_output_root, f"network_global_stats.{format}")
                    fig_network_global.savefig(output_file, dpi=dpi,  bbox_inches='tight')
            
            print(f"Done with {self.idx}")

        except Exception as e:
            traceback.print_exception(e)

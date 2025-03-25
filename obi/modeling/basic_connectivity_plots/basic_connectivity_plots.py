from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.core.base import NamedPath

class BasicConnectivityPlots(Form):
    """
    Class to generate basic connectivity plots and stats from a ConnectivityMatrix object.
    """

    _single_coord_class_name = "BasicConnectivityPlot"

    class Initialize(Block):
        matrix_path: NamedPath | list[NamedPath]
        # TODO: implement node population option
        # node_population: None | str | list[None | str] = None
        plot_formats:  tuple[str] = ("png", "pdf", "svg")
        dpi: int = 300

    initialize: Initialize


import os
from typing import ClassVar
import traceback

import numpy as np
import matplotlib.colors as mcolors

from conntility import ConnectivityMatrix
from connalysis.network.topology import rc_submatrix, node_degree
from connalysis.randomization import ER_model
from .helpers import *

class BasicConnectivityPlot(BasicConnectivityPlots, SingleCoordinateMixin):
    """
    """
    DEFAULT_FORMATS: ClassVar [tuple[str, ...]] = ("png", "pdf",  "svg")
    DEFAULT_RESOLUTION:  ClassVar[int] = 300

    def run(self) -> None:

        try:
            print(f"Info: Running idx {self.idx}")

            # Set plot format and resolution
            plot_formats = self.initialize.plot_formats
            dpi = self.initialize.dpi
            

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
            node_cmaps={"synapse_class":mcolors.LinearSegmentedColormap.from_list('RedBlue', ["C0", "C3"]), 
                        "layer":plt.get_cmap("Dark2"), 
                        "mtype": plt.get_cmap("GnBu")}
            fig=plot_node_stats(conn, node_cmaps)
            for format in plot_formats:
                output_file = os.path.join(self.coordinate_output_root, f"node_stats.{format}")
                fig.savefig(output_file, dpi=dpi,  bbox_inches='tight')


            ### Compute network metrics
            # Degrees of matrix and control 
            adj=conn.matrix.astype(bool)
            adj_ER=ER_model(adj)
            deg=node_degree(adj, direction=('IN', 'OUT'))
            deg_ER=node_degree(adj_ER, direction=('IN', 'OUT'))

            # Connection probabilities per pathway
            conn_probs={"full":{}, "within":{}}
            for grouping_prop in ["synapse_class", "layer", "mtype"]:
                conn_probs["full"][grouping_prop]= connection_probability_pathway(conn, grouping_prop)
                conn_probs["within"][grouping_prop]= connection_probability_within_pathway(conn, grouping_prop, max_dist=100)

            # Global connection probabilities
            global_conn_probs={"full":None, "within":None}
            global_conn_probs["full"]= compute_global_connectivity(adj, adj_ER, type="full")
            global_conn_probs["widthin"]=compute_global_connectivity(adj, adj_ER, v=conn.vertices, type="within", max_dist=100, cols=["x", "y"])
            
            ### Plot network metrics
            full_width=16 # width of the Figure TODO move out 
            fig_network_global=plot_connection_probability_stats(full_width, global_conn_probs)
            fig_network_pathway=plot_connection_probability_pathway_stats(full_width, conn_probs, deg, deg_ER)
            for format in plot_formats:
                output_file = os.path.join(self.coordinate_output_root, f"network_global_stats.{format}")
                fig_network_global.savefig(output_file, dpi=dpi,  bbox_inches='tight')
                output_file = os.path.join(self.coordinate_output_root, f"network_pathway_stats.{format}")
                fig_network_pathway.savefig(output_file, dpi=dpi,  bbox_inches='tight')
            
            print(f"Done with {self.idx}")

        except Exception as e:
            traceback.print_exception(e)

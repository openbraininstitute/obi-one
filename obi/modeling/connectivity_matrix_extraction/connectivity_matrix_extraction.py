from obi.modeling.core.form import Form
from obi.modeling.core.block import Block
from obi.modeling.core.single import SingleCoordinateMixin
from obi.modeling.circuit.circuit import CircuitPath

class ConnectivityMatrixExtractions(Form):
    """
    """

    _single_coord_class_name = "ConnectivityMatrixExtraction"

    class Initialize(Block):
        circuit_path: CircuitPath | list[CircuitPath]
        edge_population: None | str | list[None | str] = None
        node_attributes: None | tuple[str, ...] | list[None | tuple[str, ...]] = None

    initialize: Initialize


import os
from conntility.connectivity import ConnectivityMatrix
from bluepysnap import Circuit
from typing import ClassVar

class ConnectivityMatrixExtraction(ConnectivityMatrixExtractions, SingleCoordinateMixin):
    """
    """

    DEFAULT_ATTRIBUTES: ClassVar[tuple[str, ...]] = ("x", "y", "z", "mtype", "etype", "layer", "synapse_class")

    def run(self) -> None:

        try:
            print(f"Info: Running idx {self.idx}")

            output_file = os.path.join(self.coordinate_output_root, "connectivity_matrix.h5")
            assert not os.path.exists(output_file), f"Output file '{output_file}' already exists!"

            # Load circuit
            print(f"Info: Loading circuit '{self.initialize.circuit_path}'")
            c = Circuit(self.initialize.circuit_path.path)
            popul_names = c.edges.population_names
            assert len(popul_names) > 0, "Circuit does not have any edge populations!"
            edge_popul = self.initialize.edge_population
            if edge_popul is None:
                assert len(popul_names) == 1, "Multiple edge populations found - please specify name of edge population 'edge_popul' to extract connectivity from!"
                edge_popul = popul_names[0]  # Selecting the only one
            else:
                assert edge_popul in popul_names, f"Edge population '{edge_popul}' not found in circuit!"

            # Extract connectivity matrix
            if self.initialize.node_attributes is None:
                node_props = self.DEFAULT_ATTRIBUTES
            else:
                node_props = self.initialize.node_attributes
            load_cfg = {
                "loading":{
                    "properties": node_props,
                }
            }
            print(f"Info: Node properties to extract: {node_props}")
            print(f"Info: Extracting connectivity from edge population '{edge_popul}'")
            dummy_edge_prop = next(filter(lambda x: "@" not in x, c.edges[edge_popul].property_names))  # Select any existing edge property w/o "@"
            cmat = ConnectivityMatrix.from_bluepy(c, load_cfg, connectome=edge_popul, edge_property=dummy_edge_prop, agg_func=len)
            # Note: edge_property=<any property> and agg_func=len required to obtain the number of synapses per connection

            # Save to file
            cmat.to_h5(output_file)
            if os.path.exists(output_file):
                print(f"Info: Connectivity matrix successfully written to '{output_file}'")

        except Exception as e:
            print(f"Error: {e}")

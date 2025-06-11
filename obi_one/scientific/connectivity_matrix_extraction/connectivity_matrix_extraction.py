import logging
import os
import warnings
from typing import ClassVar

from bluepysnap import Circuit

L = logging.getLogger(__name__)

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.path import NamedPath
from obi_one.core.single import SingleCoordinateMixin

try:
    from conntility.connectivity import ConnectivityMatrix
except ImportError:
    warnings.warn("Connectome functionalities not available", UserWarning, stacklevel=1)


class ConnectivityMatrixExtractions(Form):
    """ """

    single_coord_class_name: ClassVar[str] = "ConnectivityMatrixExtraction"
    name: ClassVar[str] = "Connectivity Matrix Extraction"
    description: ClassVar[str] = (
        "Extracts a connectivity matrix of a given edge population of a SONATA circuit in ConnectomeUtilities format, consisting of a sparse connectivity matrix with the number of synapses for each connection, together with a table (dataframe) of selected node attributes."
    )

    class Initialize(Block):
        circuit_path: NamedPath | list[NamedPath]
        edge_population: None | str | list[None | str] = None
        node_attributes: None | tuple[str, ...] | list[None | tuple[str, ...]] = None

    initialize: Initialize


class ConnectivityMatrixExtraction(ConnectivityMatrixExtractions, SingleCoordinateMixin):
    """Extracts a connectivity matrix of a given edge population of a SONATA circuit in ConnectomeUtilities format,
    consisting of a sparse connectivity matrix with the number of synapses for each connection, together with a
    table (dataframe) of selected node attributes.
    """

    DEFAULT_ATTRIBUTES: ClassVar[tuple[str, ...]] = (
        "x",
        "y",
        "z",
        "mtype",
        "etype",
        "layer",
        "synapse_class",
    )

    def run(self) -> None:
        try:
            L.info(f"Info: Running idx {self.idx}")

            output_file = os.path.join(self.coordinate_output_root, "connectivity_matrix.h5")
            assert not os.path.exists(output_file), f"Output file '{output_file}' already exists!"

            # Load circuit
            L.info(f"Info: Loading circuit '{self.initialize.circuit_path}'")
            c = Circuit(self.initialize.circuit_path.path)
            popul_names = c.edges.population_names
            assert len(popul_names) > 0, "Circuit does not have any edge populations!"
            edge_popul = self.initialize.edge_population
            if edge_popul is None:
                assert len(popul_names) == 1, (
                    "Multiple edge populations found - please specify name of edge population 'edge_popul' to extract connectivity from!"
                )
                edge_popul = popul_names[0]  # Selecting the only one
            else:
                assert edge_popul in popul_names, (
                    f"Edge population '{edge_popul}' not found in circuit!"
                )

            # Extract connectivity matrix
            if self.initialize.node_attributes is None:
                node_props = self.DEFAULT_ATTRIBUTES
            else:
                node_props = self.initialize.node_attributes
            load_cfg = {
                "loading": {
                    "properties": node_props,
                }
            }
            L.info(f"Node properties to extract: {node_props}")
            L.info(f"Extracting connectivity from edge population '{edge_popul}'")
            dummy_edge_prop = next(
                filter(lambda x: "@" not in x, c.edges[edge_popul].property_names)
            )  # Select any existing edge property w/o "@"
            cmat = ConnectivityMatrix.from_bluepy(
                c, load_cfg, connectome=edge_popul, edge_property=dummy_edge_prop, agg_func=len
            )
            # Note: edge_property=<any property> and agg_func=len required to obtain the number of synapses per connection

            # Save to file
            cmat.to_h5(output_file)
            if os.path.exists(output_file):
                L.info(f"Connectivity matrix successfully written to '{output_file}'")

        except Exception as e:
            L.error(f"Error: {e}")

import logging
import warnings
from pathlib import Path
from typing import ClassVar

import entitysdk.client

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.library.circuit import Circuit

L = logging.getLogger(__name__)

try:
    from conntility.connectivity import ConnectivityMatrix
except ImportError:
    warnings.warn("Connectome functionalities not available", UserWarning, stacklevel=1)


class ConnectivityMatrixExtractionScanConfig(ScanConfig):
    """ScanConfig for extracting connectivity matrices in ConnectomeUtilities format.

    The connectivity matrix is extracted in ConnectomeUtilities format, consisting of a sparse
    connectivity matrix with the number of synapses for each connection, together with a
    table (dataframe) of selected node attributes.
    """

    single_coord_class_name: ClassVar[str] = "ConnectivityMatrixExtractionSingleConfig"
    name: ClassVar[str] = "Connectivity Matrix Extraction"
    description: ClassVar[str] = (
        "Extracts a connectivity matrix of a given edge population of a SONATA circuit in"
        " ConnectomeUtilities format, consisting of a sparse connectivity matrix with the"
        " number of synapses for each connection, together with a table (dataframe) of"
        " selected node attributes."
    )

    class Initialize(Block):
        circuit: Circuit | list[Circuit]
        edge_population: str | list[str | None] | None = None
        node_attributes: tuple[str, ...] | list[tuple[str, ...] | None] | None = None

    initialize: Initialize


class ConnectivityMatrixExtractionSingleConfig(
    ConnectivityMatrixExtractionScanConfig, SingleConfigMixin
):
    """Extracts a connectivity matrix of a given edge population of a SONATA circuit."""


class ConnectivityMatrixExtractionTask(Task):
    config: ConnectivityMatrixExtractionSingleConfig

    DEFAULT_ATTRIBUTES: ClassVar[tuple[str, ...]] = (
        "x",
        "y",
        "z",
        "mtype",
        "etype",
        "layer",
        "synapse_class",
    )

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
    ) -> None:
        L.info(f"Info: Running idx {self.config.idx}")

        output_file = Path(self.config.coordinate_output_root) / "connectivity_matrix.h5"
        if Path(output_file).exists():
            msg = f"Output file '{output_file}' already exists!"
            raise ValueError(msg)

        # Load circuit
        L.info(f"Info: Loading circuit '{self.config.initialize.circuit}'")
        c = self.config.initialize.circuit.sonata_circuit
        popul_names = c.edges.population_names
        if len(popul_names) == 0:
            msg = "Circuit does not have any edge populations!"
            raise ValueError(msg)
        edge_popul = self.config.initialize.edge_population
        if edge_popul is None:
            if len(popul_names) != 1:
                msg = (
                    "Multiple edge populations found - please specify name of edge population"
                    " 'edge_popul' to extract connectivity from!"
                )
                raise ValueError(msg)
            edge_popul = popul_names[0]  # Selecting the only one
        elif edge_popul not in popul_names:
            msg = f"Edge population '{edge_popul}' not found in circuit!"
            raise ValueError(msg)

        # Extract connectivity matrix
        if self.config.initialize.node_attributes is None:
            node_props = self.DEFAULT_ATTRIBUTES
        else:
            node_props = self.config.initialize.node_attributes
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
        # Note: edge_property=<any property> and agg_func=len required to obtain the number
        # of synapses per connection

        # Save to file
        cmat.to_h5(output_file)
        if Path(output_file).exists():
            L.info(f"Connectivity matrix successfully written to '{output_file}'")

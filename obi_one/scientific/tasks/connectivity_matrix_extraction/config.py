"""Connectivity matrix extraction task configuration."""

from typing import ClassVar

from obi_one.core.block import Block
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.library.circuit import Circuit


class ConnectivityMatrixExtractionScanConfig(ScanConfig):
    """ScanConfig for extracting connectivity matrices in ConnectomeUtilities format.

    The connectivity matrix is extracted in ConnectomeUtilities format, consisting of a sparse
    connectivity matrix with the number of synapses for each connection, together with a
    table (dataframe) of selected node attributes.
    """

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
        with_matrix_config: bool = False

    initialize: Initialize


class ConnectivityMatrixExtractionSingleConfig(
    ConnectivityMatrixExtractionScanConfig, SingleConfigMixin
):
    """Extracts a connectivity matrix of a given edge population of a SONATA circuit."""

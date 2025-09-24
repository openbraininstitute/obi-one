from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlots
from obi_one.scientific.tasks.circuit_extraction import CircuitExtractions
from obi_one.scientific.tasks.connectivity_matrix_extraction import ConnectivityMatrixExtractions
from obi_one.scientific.tasks.simulations import SimulationsForm

ScanConfigsUnion = Annotated[
    SimulationsForm | CircuitExtractions | BasicConnectivityPlots | ConnectivityMatrixExtractions,
    Discriminator("type"),
]

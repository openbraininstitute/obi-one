from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.circuit_extraction import CircuitExtractions
from obi_one.scientific.tasks.example_task_1 import ExampleScanConfig
from obi_one.scientific.tasks.example_task_2 import ExampleScanConfig2
from obi_one.scientific.tasks.simulations import SimulationsForm
from obi_one.scientific.tasks.basic_connectivity_plots import BasicConnectivityPlots

ScanConfigsUnion = Annotated[
    ExampleScanConfig | ExampleScanConfig2 | SimulationsForm | CircuitExtractions | BasicConnectivityPlots,
    Discriminator("type"),
]

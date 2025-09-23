from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks.example_task_1 import ExampleScanConfig
from obi_one.scientific.tasks.example_task_2 import ExampleScanConfig2
from obi_one.scientific.tasks.simulations import SimulationsForm

ScanConfigsUnion = Annotated[
    ExampleScanConfig | ExampleScanConfig2 | SimulationsForm,
    Discriminator("type"),
]

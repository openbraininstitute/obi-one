from typing import Annotated

from pydantic import Discriminator

from obi_one.scientific.tasks_and_configs.example_task_1 import ExampleScanConfig
from obi_one.scientific.tasks_and_configs.example_task_2 import ExampleScanConfig2

ScanConfigsUnion = Annotated[
    ExampleScanConfig | ExampleScanConfig2,
    Discriminator("type"),
]

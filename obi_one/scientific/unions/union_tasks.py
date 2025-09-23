from typing import Annotated, get_args

from pydantic import Discriminator

from obi_one.scientific.tasks.example_task_1 import ExampleScanConfig
from obi_one.scientific.tasks.example_task_2 import ExampleScanConfig2
from obi_one.scientific.tasks.simulations import SimulationsForm

TasksUnion = Annotated[
    ExampleScanConfig | ExampleScanConfig2 | SimulationsForm,
    Discriminator("type"),
]

_task_configs_map = {task.__name__: type(task.config) for task in get_args(TasksUnion)}


def get_task_config_type(task: TasksUnion) -> type:
    return _task_configs_map[task.__name__]

from typing import Annotated, get_args

from pydantic import Discriminator

from obi_one.scientific.tasks.example_task_1 import ExampleTask
from obi_one.scientific.tasks.example_task_2 import ExampleTask2
from obi_one.scientific.tasks.simulations import GenerateSimulationTask

TasksUnion = Annotated[
    ExampleTask | ExampleTask2 | GenerateSimulationTask,
    Discriminator("type"),
]

inner, *_ = get_args(TasksUnion)
task_types = get_args(inner)

_task_configs_map = {task.__name__: task.model_fields["config"].annotation for task in task_types}
_config_tasks_map = {task.model_fields["config"].annotation: task for task in task_types}


def get_tasks_config_type(task: TasksUnion) -> type:
    return _task_configs_map[task.__name__]


def get_configs_task_type(config: object) -> type:
    return _config_tasks_map[config.__class__]

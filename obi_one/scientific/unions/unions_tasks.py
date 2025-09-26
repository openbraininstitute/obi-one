from typing import Annotated, get_args

from pydantic import Discriminator

from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsTask,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import ConnectivityMatrixExtractionTask
from obi_one.scientific.tasks.contribute import ContributeMorphologyTask
from obi_one.scientific.tasks.ephys_extraction_task import ElectrophysiologyMetricsTask
from obi_one.scientific.tasks.folder_compression import FolderCompressionTask
from obi_one.scientific.tasks.morphology_containerization import MorphologyContainerizationTask
from obi_one.scientific.tasks.morphology_decontainerization import MorphologyDecontainerizationTask
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsTask
from obi_one.scientific.tasks.morphology_metrics_task import MorphologyMetricsTask
from obi_one.scientific.tasks.simulations import GenerateSimulationTask

TasksUnion = Annotated[
    GenerateSimulationTask
    | CircuitExtractionTask
    | ContributeMorphologyTask
    | BasicConnectivityPlotsTask
    | ConnectivityMatrixExtractionTask
    | ElectrophysiologyMetricsTask
    | FolderCompressionTask
    | MorphologyContainerizationTask
    | MorphologyDecontainerizationTask
    | MorphologyMetricsTask
    | MorphologyLocationsTask,
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

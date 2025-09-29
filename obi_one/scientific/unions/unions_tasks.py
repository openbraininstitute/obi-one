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
from obi_one.scientific.tasks.ephys_extraction import ElectrophysiologyMetricsTask
from obi_one.scientific.tasks.folder_compression import FolderCompressionTask
from obi_one.scientific.tasks.ion_channel_modeling import IonChannelFittingTask
from obi_one.scientific.tasks.morphology_containerization import MorphologyContainerizationTask
from obi_one.scientific.tasks.morphology_decontainerization import MorphologyDecontainerizationTask
from obi_one.scientific.tasks.morphology_locations import MorphologyLocationsTask
from obi_one.scientific.tasks.morphology_metrics import MorphologyMetricsTask
from obi_one.scientific.tasks.simulations import GenerateSimulationTask

TasksUnion = Annotated[
    GenerateSimulationTask
    | CircuitExtractionTask
    | ContributeMorphologyTask
    | BasicConnectivityPlotsTask
    | ConnectivityMatrixExtractionTask
    | ElectrophysiologyMetricsTask
    | FolderCompressionTask
    | IonChannelFittingTask
    | MorphologyContainerizationTask
    | MorphologyDecontainerizationTask
    | MorphologyMetricsTask
    | MorphologyLocationsTask,
    Discriminator("type"),
]


inner, *_ = get_args(TasksUnion)
task_types = get_args(inner)

_config_tasks_map = {
    task.model_fields["config"].annotation if "config" in task.model_fields else None: task
    for task in task_types
}

_config_tasks_map = {
    "Simulation": GenerateSimulationTask,
    "CircuitSimulationSingleConfig": GenerateSimulationTask,
    "CircuitExtractionSingleConfig": CircuitExtractionTask,
    "ContributeMorphologySingleConfig": ContributeMorphologyTask,
    "BasicConnectivityPlotsSingleConfig": BasicConnectivityPlotsTask,
    "ConnectivityMatrixExtractionSingleConfig": ConnectivityMatrixExtractionTask,
    "ElectrophysiologyMetricsSingleConfig": ElectrophysiologyMetricsTask,
    "FolderCompressionSingleConfig": FolderCompressionTask,
    "IonChannelFittingSingleConfig": IonChannelFittingTask,
    "MorphologyContainerizationSingleConfig": MorphologyContainerizationTask,
    "MorphologyDecontainerizationSingleConfig": MorphologyDecontainerizationTask,
    "MorphologyMetricsSingleConfig": MorphologyMetricsTask,
    "MorphologyLocationsSingleConfig": MorphologyLocationsTask,
}




def get_configs_task_type(config: object) -> type:
    return _config_tasks_map[type(config).__name__]

from entitysdk.types import AssetLabel

from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsSingleConfig,
    BasicConnectivityPlotsTask,
)
from obi_one.scientific.tasks.brian2_simulation_from_sonata.config import (
    Brian2SimulationFromSonataSingleConfig,
)
from obi_one.scientific.tasks.brian2_simulation_from_sonata.task import (
    Brian2SimulationFromSonataTask,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionSingleConfig,
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionSingleConfig,
    ConnectivityMatrixExtractionTask,
)
from obi_one.scientific.tasks.contribute import (
    ContributeMorphologySingleConfig,
    ContributeMorphologyTask,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingSingleConfig
from obi_one.scientific.tasks.em_synapse_mapping.task import EMSynapseMappingTask
from obi_one.scientific.tasks.ephys_extraction import (
    ElectrophysiologyMetricsSingleConfig,
    ElectrophysiologyMetricsTask,
)
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionSingleConfig,
    FolderCompressionTask,
)
from obi_one.scientific.tasks.generate_simulations.config.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.ion_channel_models import (
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.me_model import (
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.me_model_with_synapses import (
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import (
    GenerateSimulationTask,
)
from obi_one.scientific.tasks.ion_channel_model_simulation_execution import (
    IonChannelModelSimulationExecutionSingleConfig,
    IonChannelModelSimulationExecutionTask,
)
from obi_one.scientific.tasks.ion_channel_modeling import (
    IonChannelFittingSingleConfig,
    IonChannelFittingTask,
)
from obi_one.scientific.tasks.morphology_containerization import (
    MorphologyContainerizationSingleConfig,
    MorphologyContainerizationTask,
)
from obi_one.scientific.tasks.morphology_decontainerization import (
    MorphologyDecontainerizationSingleConfig,
    MorphologyDecontainerizationTask,
)
from obi_one.scientific.tasks.morphology_locations import (
    MorphologyLocationsSingleConfig,
    MorphologyLocationsTask,
)
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsSingleConfig,
    MorphologyMetricsTask,
)
from obi_one.scientific.tasks.skeletonization import (
    SkeletonizationSingleConfig,
    SkeletonizationTask,
)
from obi_one.types import TaskType

_config_tasks_map = {
    CircuitSimulationSingleConfig: GenerateSimulationTask,
    CircuitExtractionSingleConfig: CircuitExtractionTask,
    MEModelSimulationSingleConfig: GenerateSimulationTask,
    ContributeMorphologySingleConfig: ContributeMorphologyTask,
    BasicConnectivityPlotsSingleConfig: BasicConnectivityPlotsTask,
    ConnectivityMatrixExtractionSingleConfig: ConnectivityMatrixExtractionTask,
    ElectrophysiologyMetricsSingleConfig: ElectrophysiologyMetricsTask,
    FolderCompressionSingleConfig: FolderCompressionTask,
    IonChannelFittingSingleConfig: IonChannelFittingTask,
    MorphologyContainerizationSingleConfig: MorphologyContainerizationTask,
    MorphologyDecontainerizationSingleConfig: MorphologyDecontainerizationTask,
    MorphologyMetricsSingleConfig: MorphologyMetricsTask,
    MorphologyLocationsSingleConfig: MorphologyLocationsTask,
    MEModelWithSynapsesCircuitSimulationSingleConfig: GenerateSimulationTask,
    SkeletonizationSingleConfig: SkeletonizationTask,
    EMSynapseMappingSingleConfig: EMSynapseMappingTask,
    IonChannelModelSimulationSingleConfig: GenerateSimulationTask,
    Brian2CircuitSimulationSingleConfig: GenerateSimulationTask,
    Brian2SimulationFromSonataSingleConfig: Brian2SimulationFromSonataTask,
}
_task_type_task_map = {
    TaskType.circuit_extraction: CircuitExtractionTask,
    TaskType.ion_channel_model_simulation_execution: IonChannelModelSimulationExecutionTask,
    TaskType.morphology_skeletonization: SkeletonizationTask,
    TaskType.em_synapse_mapping: EMSynapseMappingTask,
}
_task_type_single_config_map = {
    TaskType.circuit_extraction: CircuitExtractionSingleConfig,
    TaskType.ion_channel_model_simulation_execution: IonChannelModelSimulationExecutionSingleConfig,
    TaskType.morphology_skeletonization: SkeletonizationSingleConfig,
    TaskType.em_synapse_mapping: EMSynapseMappingSingleConfig,
}
_task_type_config_asset_label_map = {
    TaskType.circuit_extraction: AssetLabel.task_config,
    TaskType.morphology_skeletonization: AssetLabel.task_config,
    TaskType.circuit_simulation: None,
    TaskType.ion_channel_model_simulation_execution: None,
    TaskType.em_synapse_mapping: AssetLabel.task_config,
}


def get_configs_task_type(config: object) -> type:
    return _config_tasks_map[config.__class__]


def get_task_type(task_type: TaskType) -> type:
    return _task_type_task_map[task_type]


def get_task_type_single_config(task_type: TaskType) -> type:
    return _task_type_single_config_map[task_type]


def get_task_type_config_asset_label(task_type: TaskType) -> AssetLabel | None:
    return _task_type_config_asset_label_map[task_type]

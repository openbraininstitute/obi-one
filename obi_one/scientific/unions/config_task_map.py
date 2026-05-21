from entitysdk.types import AssetLabel

from obi_one.core.registry import task_registry
from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsSingleConfig,
    BasicConnectivityPlotsTask,
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
from obi_one.scientific.tasks.create_recording_array.create_recording_array import (
    CreateExtracellularRecordingArraySingleConfig,
    CreateExtracellularRecordingArrayTask,
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

# Complete task registry: single_config_cls -> (task_cls, task_type, asset_label)
# task_type and asset_label are None for tasks not launchable via the API.
TASK_MAP: dict[type, tuple[type, TaskType | None, AssetLabel | None]] = {
    BasicConnectivityPlotsSingleConfig: (
        BasicConnectivityPlotsTask,
        None,
        None,
    ),
    CircuitExtractionSingleConfig: (
        CircuitExtractionTask,
        TaskType.circuit_extraction,
        AssetLabel.task_config,
    ),
    CircuitSimulationSingleConfig: (
        GenerateSimulationTask,
        TaskType.circuit_simulation,
        None,
    ),
    ConnectivityMatrixExtractionSingleConfig: (
        ConnectivityMatrixExtractionTask,
        None,
        None,
    ),
    ContributeMorphologySingleConfig: (
        ContributeMorphologyTask,
        None,
        None,
    ),
    CreateExtracellularRecordingArraySingleConfig: (
        CreateExtracellularRecordingArrayTask,
        None,
        None,
    ),
    ElectrophysiologyMetricsSingleConfig: (
        ElectrophysiologyMetricsTask,
        None,
        None,
    ),
    EMSynapseMappingSingleConfig: (
        EMSynapseMappingTask,
        TaskType.em_synapse_mapping,
        AssetLabel.task_config,
    ),
    FolderCompressionSingleConfig: (
        FolderCompressionTask,
        None,
        None,
    ),
    IonChannelFittingSingleConfig: (
        IonChannelFittingTask,
        None,
        None,
    ),
    IonChannelModelSimulationExecutionSingleConfig: (
        IonChannelModelSimulationExecutionTask,
        TaskType.ion_channel_model_simulation_execution,
        None,
    ),
    IonChannelModelSimulationSingleConfig: (
        GenerateSimulationTask,
        None,
        None,
    ),
    MEModelSimulationSingleConfig: (
        GenerateSimulationTask,
        None,
        None,
    ),
    MEModelWithSynapsesCircuitSimulationSingleConfig: (
        GenerateSimulationTask,
        None,
        None,
    ),
    MorphologyContainerizationSingleConfig: (
        MorphologyContainerizationTask,
        None,
        None,
    ),
    MorphologyDecontainerizationSingleConfig: (
        MorphologyDecontainerizationTask,
        None,
        None,
    ),
    MorphologyLocationsSingleConfig: (
        MorphologyLocationsTask,
        None,
        None,
    ),
    MorphologyMetricsSingleConfig: (
        MorphologyMetricsTask,
        None,
        None,
    ),
    SkeletonizationSingleConfig: (
        SkeletonizationTask,
        TaskType.morphology_skeletonization,
        AssetLabel.task_config,
    ),
}

# Populate the registry from the static map
for single_config_cls, (task_cls, task_type, asset_label) in TASK_MAP.items():
    task_registry.register_task(
        task_cls=task_cls,
        single_config_cls=single_config_cls,
        task_type=task_type,
        asset_label=asset_label,
    )


# Backward-compatible convenience functions (delegate to the registry)


def get_configs_task_type(config: object) -> type:
    return task_registry.get_configs_task_type(config)


def get_task_type(task_type: TaskType) -> type:
    return task_registry.get_task_type(task_type)


def get_task_type_single_config(task_type: TaskType) -> type:
    return task_registry.get_task_type_single_config(task_type)


def get_task_type_config_asset_label(task_type: TaskType) -> AssetLabel | None:
    return task_registry.get_task_type_config_asset_label(task_type)

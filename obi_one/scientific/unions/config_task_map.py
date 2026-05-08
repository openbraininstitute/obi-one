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


def _populate_registry() -> None:
    """Populate the core TaskRegistry with all scientific task mappings.

    This allows core/run_tasks.py to look up task classes, single configs,
    and asset labels without importing scientific modules directly.
    Called once at module load time.
    """
    # Config class -> Task class
    task_registry.register_config_task(CircuitSimulationSingleConfig, GenerateSimulationTask)
    task_registry.register_config_task(CircuitExtractionSingleConfig, CircuitExtractionTask)
    task_registry.register_config_task(MEModelSimulationSingleConfig, GenerateSimulationTask)
    task_registry.register_config_task(ContributeMorphologySingleConfig, ContributeMorphologyTask)
    task_registry.register_config_task(
        BasicConnectivityPlotsSingleConfig, BasicConnectivityPlotsTask
    )
    task_registry.register_config_task(
        ConnectivityMatrixExtractionSingleConfig, ConnectivityMatrixExtractionTask
    )
    task_registry.register_config_task(
        ElectrophysiologyMetricsSingleConfig, ElectrophysiologyMetricsTask
    )
    task_registry.register_config_task(FolderCompressionSingleConfig, FolderCompressionTask)
    task_registry.register_config_task(IonChannelFittingSingleConfig, IonChannelFittingTask)
    task_registry.register_config_task(
        MorphologyContainerizationSingleConfig, MorphologyContainerizationTask
    )
    task_registry.register_config_task(
        MorphologyDecontainerizationSingleConfig, MorphologyDecontainerizationTask
    )
    task_registry.register_config_task(MorphologyMetricsSingleConfig, MorphologyMetricsTask)
    task_registry.register_config_task(MorphologyLocationsSingleConfig, MorphologyLocationsTask)
    task_registry.register_config_task(
        MEModelWithSynapsesCircuitSimulationSingleConfig, GenerateSimulationTask
    )
    task_registry.register_config_task(SkeletonizationSingleConfig, SkeletonizationTask)
    task_registry.register_config_task(EMSynapseMappingSingleConfig, EMSynapseMappingTask)
    task_registry.register_config_task(
        IonChannelModelSimulationSingleConfig, GenerateSimulationTask
    )

    # TaskType -> Task class
    task_registry.register_task_type(TaskType.circuit_extraction, CircuitExtractionTask)
    task_registry.register_task_type(
        TaskType.ion_channel_model_simulation_execution, IonChannelModelSimulationExecutionTask
    )
    task_registry.register_task_type(TaskType.morphology_skeletonization, SkeletonizationTask)
    task_registry.register_task_type(TaskType.em_synapse_mapping, EMSynapseMappingTask)

    # TaskType -> SingleConfig class
    task_registry.register_task_type_single_config(
        TaskType.circuit_extraction, CircuitExtractionSingleConfig
    )
    task_registry.register_task_type_single_config(
        TaskType.ion_channel_model_simulation_execution,
        IonChannelModelSimulationExecutionSingleConfig,
    )
    task_registry.register_task_type_single_config(
        TaskType.morphology_skeletonization, SkeletonizationSingleConfig
    )
    task_registry.register_task_type_single_config(
        TaskType.em_synapse_mapping, EMSynapseMappingSingleConfig
    )

    # TaskType -> config asset label
    task_registry.register_task_type_config_asset_label(
        TaskType.circuit_extraction, AssetLabel.task_config
    )
    task_registry.register_task_type_config_asset_label(
        TaskType.morphology_skeletonization, AssetLabel.task_config
    )
    task_registry.register_task_type_config_asset_label(TaskType.circuit_simulation, None)
    task_registry.register_task_type_config_asset_label(
        TaskType.ion_channel_model_simulation_execution, None
    )
    task_registry.register_task_type_config_asset_label(
        TaskType.em_synapse_mapping, AssetLabel.task_config
    )


# Runs exactly once at module load (cached for subsequent imports).
_populate_registry()


# Backward-compatible convenience functions (delegate to the registry)


def get_configs_task_type(config: object) -> type:
    return task_registry.get_configs_task_type(config)


def get_task_type(task_type: TaskType) -> type:
    return task_registry.get_task_type(task_type)


def get_task_type_single_config(task_type: TaskType) -> type:
    return task_registry.get_task_type_single_config(task_type)


def get_task_type_config_asset_label(task_type: TaskType) -> AssetLabel | None:
    return task_registry.get_task_type_config_asset_label(task_type)

from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

from obi_one.core.registry import TaskRegistration, task_registry
from obi_one.scientific.tasks.basic_connectivity_plots import (
    BasicConnectivityPlotsScanConfig,
    BasicConnectivityPlotsSingleConfig,
    BasicConnectivityPlotsTask,
)
from obi_one.scientific.tasks.build_synaptome import (
    MEModelSynapticModelPlacementScanConfig,
    MEModelSynapticModelPlacementSingleConfig,
    MEModelSynapticModelPlacementTask,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionScanConfig,
    CircuitExtractionSingleConfig,
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.connectivity_matrix_extraction import (
    ConnectivityMatrixExtractionScanConfig,
    ConnectivityMatrixExtractionSingleConfig,
    ConnectivityMatrixExtractionTask,
)
from obi_one.scientific.tasks.create_recording_array.create_recording_array import (
    CreateExtracellularRecordingArrayScanConfig,
    CreateExtracellularRecordingArraySingleConfig,
    CreateExtracellularRecordingArrayTask,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import (
    EMSynapseMappingScanConfig,
    EMSynapseMappingSingleConfig,
)
from obi_one.scientific.tasks.em_synapse_mapping.task import EMSynapseMappingTask
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
    EModelEFeatureExtractionScanConfig,
    EModelEFeatureExtractionSingleConfig,
)
from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
    EModelEFeatureExtractionTask,
)
from obi_one.scientific.tasks.ephys_extraction import (
    ElectrophysiologyMetricsScanConfig,
    ElectrophysiologyMetricsSingleConfig,
    ElectrophysiologyMetricsTask,
)
from obi_one.scientific.tasks.folder_compression import (
    FolderCompressionScanConfig,
    FolderCompressionSingleConfig,
    FolderCompressionTask,
)
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationScanConfig,
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit import (
    LearningEngineCircuitSimulationScanConfig,
    LearningEngineCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationScanConfig,
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationScanConfig,
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationScanConfig,
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # ruff: ignore[line-too-long]
    MEModelWithSynapsesCircuitSimulationScanConfig,
    MEModelWithSynapsesCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import (
    GenerateSimulationTask,
)
from obi_one.scientific.tasks.ion_channel_modeling import (
    IonChannelFittingScanConfig,
    IonChannelFittingSingleConfig,
    IonChannelFittingTask,
)
from obi_one.scientific.tasks.mesh_lod_generation.config import (
    MeshLodGenerationSingleConfig,
)
from obi_one.scientific.tasks.mesh_lod_generation.task import MeshLODGenerationTask
from obi_one.scientific.tasks.morphology_containerization import (
    MorphologyContainerizationScanConfig,
    MorphologyContainerizationSingleConfig,
    MorphologyContainerizationTask,
)
from obi_one.scientific.tasks.morphology_decontainerization import (
    MorphologyDecontainerizationScanConfig,
    MorphologyDecontainerizationSingleConfig,
    MorphologyDecontainerizationTask,
)
from obi_one.scientific.tasks.morphology_locations import (
    MorphologyLocationsScanConfig,
    MorphologyLocationsSingleConfig,
    MorphologyLocationsTask,
)
from obi_one.scientific.tasks.morphology_metrics import (
    MorphologyMetricsScanConfig,
    MorphologyMetricsSingleConfig,
    MorphologyMetricsTask,
)
from obi_one.scientific.tasks.simulation_execution import (
    CircuitSimulationExecutionSingleConfig,
    CircuitSimulationExecutionTask,
    IonChannelModelSimulationExecutionSingleConfig,
    IonChannelModelSimulationExecutionTask,
    SingleNeuronSimulationExecutionSingleConfig,
    SingleNeuronSimulationExecutionTask,
    SingleNeuronSynaptomeSimulationExecutionSingleConfig,
    SingleNeuronSynaptomeSimulationExecutionTask,
)
from obi_one.scientific.tasks.skeletonization import (
    SkeletonizationScanConfig,
    SkeletonizationSingleConfig,
    SkeletonizationTask,
)
from obi_one.scientific.tasks.synapse_parameterization.config import (
    SynapseParameterizationScanConfig,
    SynapseParameterizationSingleConfig,
)
from obi_one.scientific.tasks.synapse_parameterization.task import SynapseParameterizationTask
from obi_one.types import TaskType

# Task registry: TaskType -> TaskRegistration.
# asset_label is None for tasks that receive their config inline. The TaskConfig and
# TaskActivity types are set only for tasks registered against the database.
TASK_MAP: dict[TaskType, TaskRegistration] = {
    # API-launchable tasks (submitted via the launch-system)
    TaskType.circuit_extraction: TaskRegistration(
        task_cls=CircuitExtractionTask,
        single_config_cls=CircuitExtractionSingleConfig,
        scan_config_cls=CircuitExtractionScanConfig,
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.circuit_extraction__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.circuit_extraction__config_generation
        ),
        single_task_config_type=TaskConfigType.circuit_extraction__config,
        single_task_activity_type=TaskActivityType.circuit_extraction__execution,
    ),
    TaskType.circuit_simulation: TaskRegistration(
        task_cls=GenerateSimulationTask,
        single_config_cls=CircuitSimulationSingleConfig,
        scan_config_cls=CircuitSimulationScanConfig,
        asset_label=None,
    ),
    TaskType.circuit_synaptic_physiology_assignment: TaskRegistration(
        task_cls=SynapseParameterizationTask,
        single_config_cls=SynapseParameterizationSingleConfig,
        scan_config_cls=SynapseParameterizationScanConfig,
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.circuit_synaptic_physiology_assignment__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.circuit_synaptic_physiology_assignment__config_generation
        ),
        single_task_config_type=TaskConfigType.circuit_synaptic_physiology_assignment__config,
        single_task_activity_type=(
            TaskActivityType.circuit_synaptic_physiology_assignment__execution
        ),
    ),
    TaskType.em_synapse_mapping: TaskRegistration(
        task_cls=EMSynapseMappingTask,
        single_config_cls=EMSynapseMappingSingleConfig,
        scan_config_cls=EMSynapseMappingScanConfig,
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.em_synapse_mapping__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.em_synapse_mapping__config_generation
        ),
        single_task_config_type=TaskConfigType.em_synapse_mapping__config,
        single_task_activity_type=TaskActivityType.em_synapse_mapping__execution,
    ),
    TaskType.efeature_extraction: TaskRegistration(
        task_cls=EModelEFeatureExtractionTask,
        single_config_cls=EModelEFeatureExtractionSingleConfig,
        scan_config_cls=EModelEFeatureExtractionScanConfig,
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=(TaskConfigType.efeature_extraction__campaign),
        campaign_generation_task_activity_type=(
            TaskActivityType.efeature_extraction__config_generation
        ),
        single_task_config_type=TaskConfigType.efeature_extraction__config,
        single_task_activity_type=(TaskActivityType.efeature_extraction__execution),
    ),
    TaskType.extracellular_recording_weights_calculation: TaskRegistration(
        task_cls=CreateExtracellularRecordingArrayTask,
        single_config_cls=CreateExtracellularRecordingArraySingleConfig,
        scan_config_cls=CreateExtracellularRecordingArrayScanConfig,
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=(
            TaskConfigType.extracellular_recording_weights_calculation__campaign
        ),
        campaign_generation_task_activity_type=(
            TaskActivityType.extracellular_recording_weights_calculation__config_generation
        ),
        single_task_config_type=TaskConfigType.extracellular_recording_weights_calculation__config,
        single_task_activity_type=(
            TaskActivityType.extracellular_recording_weights_calculation__execution
        ),
    ),
    TaskType.ion_channel_model_simulation_execution: TaskRegistration(
        task_cls=IonChannelModelSimulationExecutionTask,
        single_config_cls=IonChannelModelSimulationExecutionSingleConfig,
        asset_label=None,
    ),
    TaskType.single_neuron_simulation_execution: TaskRegistration(
        task_cls=SingleNeuronSimulationExecutionTask,
        single_config_cls=SingleNeuronSimulationExecutionSingleConfig,
        asset_label=None,
    ),
    TaskType.single_neuron_synaptome_simulation_execution: TaskRegistration(
        task_cls=SingleNeuronSynaptomeSimulationExecutionTask,
        single_config_cls=SingleNeuronSynaptomeSimulationExecutionSingleConfig,
        asset_label=None,
    ),
    TaskType.mesh_lod_generation: TaskRegistration(
        task_cls=MeshLODGenerationTask,
        single_config_cls=MeshLodGenerationSingleConfig,
        asset_label=AssetLabel.task_config,
        single_task_config_type=TaskConfigType.mesh_lod_generation__config,
        single_task_activity_type=TaskActivityType.mesh_lod_generation__execution,
    ),
    TaskType.morphology_skeletonization: TaskRegistration(
        task_cls=SkeletonizationTask,
        single_config_cls=SkeletonizationSingleConfig,
        scan_config_cls=SkeletonizationScanConfig,
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.skeletonization__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.skeletonization__config_generation
        ),
        single_task_config_type=TaskConfigType.skeletonization__config,
        single_task_activity_type=TaskActivityType.skeletonization__execution,
    ),
    # Local-only tasks (executed via scan generation / direct dispatch)
    TaskType.basic_connectivity_plots: TaskRegistration(
        task_cls=BasicConnectivityPlotsTask,
        single_config_cls=BasicConnectivityPlotsSingleConfig,
        scan_config_cls=BasicConnectivityPlotsScanConfig,
        asset_label=None,
    ),
    TaskType.brian2_circuit_simulation: TaskRegistration(
        task_cls=GenerateSimulationTask,
        single_config_cls=Brian2CircuitSimulationSingleConfig,
        scan_config_cls=Brian2CircuitSimulationScanConfig,
        asset_label=None,
    ),
    TaskType.connectivity_matrix_extraction: TaskRegistration(
        task_cls=ConnectivityMatrixExtractionTask,
        single_config_cls=ConnectivityMatrixExtractionSingleConfig,
        scan_config_cls=ConnectivityMatrixExtractionScanConfig,
        asset_label=None,
    ),
    TaskType.electrophysiology_metrics: TaskRegistration(
        task_cls=ElectrophysiologyMetricsTask,
        single_config_cls=ElectrophysiologyMetricsSingleConfig,
        scan_config_cls=ElectrophysiologyMetricsScanConfig,
        asset_label=None,
    ),
    TaskType.folder_compression: TaskRegistration(
        task_cls=FolderCompressionTask,
        single_config_cls=FolderCompressionSingleConfig,
        scan_config_cls=FolderCompressionScanConfig,
        asset_label=None,
    ),
    TaskType.ion_channel_fitting: TaskRegistration(
        task_cls=IonChannelFittingTask,
        single_config_cls=IonChannelFittingSingleConfig,
        scan_config_cls=IonChannelFittingScanConfig,
        asset_label=None,
    ),
    TaskType.ion_channel_model_simulation: TaskRegistration(
        task_cls=GenerateSimulationTask,
        single_config_cls=IonChannelModelSimulationSingleConfig,
        scan_config_cls=IonChannelModelSimulationScanConfig,
        asset_label=None,
    ),
    TaskType.me_model_simulation: TaskRegistration(
        task_cls=GenerateSimulationTask,
        single_config_cls=MEModelSimulationSingleConfig,
        scan_config_cls=MEModelSimulationScanConfig,
        asset_label=None,
    ),
    TaskType.learning_engine_circuit_simulation: TaskRegistration(
        task_cls=GenerateSimulationTask,
        single_config_cls=LearningEngineCircuitSimulationSingleConfig,
        scan_config_cls=LearningEngineCircuitSimulationScanConfig,
        asset_label=None,
    ),
    TaskType.me_model_with_synapses_circuit_simulation: TaskRegistration(
        task_cls=GenerateSimulationTask,
        single_config_cls=MEModelWithSynapsesCircuitSimulationSingleConfig,
        scan_config_cls=MEModelWithSynapsesCircuitSimulationScanConfig,
        asset_label=None,
    ),
    TaskType.morphology_containerization: TaskRegistration(
        task_cls=MorphologyContainerizationTask,
        single_config_cls=MorphologyContainerizationSingleConfig,
        scan_config_cls=MorphologyContainerizationScanConfig,
        asset_label=None,
    ),
    TaskType.morphology_decontainerization: TaskRegistration(
        task_cls=MorphologyDecontainerizationTask,
        single_config_cls=MorphologyDecontainerizationSingleConfig,
        scan_config_cls=MorphologyDecontainerizationScanConfig,
        asset_label=None,
    ),
    TaskType.morphology_locations: TaskRegistration(
        task_cls=MorphologyLocationsTask,
        single_config_cls=MorphologyLocationsSingleConfig,
        scan_config_cls=MorphologyLocationsScanConfig,
        asset_label=None,
    ),
    TaskType.morphology_metrics: TaskRegistration(
        task_cls=MorphologyMetricsTask,
        single_config_cls=MorphologyMetricsSingleConfig,
        scan_config_cls=MorphologyMetricsScanConfig,
        asset_label=None,
    ),
    TaskType.circuit_simulation_neurodamus_machine: TaskRegistration(
        task_cls=CircuitSimulationExecutionTask,
        single_config_cls=CircuitSimulationExecutionSingleConfig,
        asset_label=None,
    ),
    TaskType.circuit_single_build: TaskRegistration(
        task_cls=MEModelSynapticModelPlacementTask,
        single_config_cls=MEModelSynapticModelPlacementSingleConfig,
        scan_config_cls=MEModelSynapticModelPlacementScanConfig,
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.circuit_single_build__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.circuit_single_build__config_generation
        ),
        single_task_config_type=TaskConfigType.circuit_single_build__config,
        single_task_activity_type=TaskActivityType.circuit_single_build__execution,
    ),
}

# Populate the registry from the static map
for task_type, registration in TASK_MAP.items():
    task_registry.register_task(task_type, registration)


# Backward-compatible convenience functions (delegate to the registry)


def get_single_configs_task_type(config: object) -> type:
    return task_registry.get_single_configs_task_type(config)


def get_task_type(task_type: TaskType) -> type:
    return task_registry.get_task_type(task_type)


def get_task_type_single_config(task_type: TaskType) -> type:
    return task_registry.get_task_type_single_config(task_type)


def get_task_type_config_asset_label(task_type: TaskType) -> AssetLabel | None:
    return task_registry.get_task_type_config_asset_label(task_type)

from entitysdk.types import AssetLabel

from obi_one.core.registry import task_registry
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.task import (
    AINDEPhysPreprocessingTask,
)
from obi_one.scientific.tasks.aind_ephys._03_kilosort4.config import (
    AINDEPhysSpikesortKilosort4SingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_kilosort4.task import (
    AINDEPhysSpikesortKilosort4Task,
)
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.config import (
    AINDEPhysPostprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.task import (
    AINDEPhysPostprocessingTask,
)
from obi_one.scientific.tasks.aind_ephys._05_curation.config import (
    AINDEPhysCurationSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._05_curation.task import (
    AINDEPhysCurationTask,
)
from obi_one.scientific.tasks.aind_ephys._06_visualization.config import (
    AINDEPhysVisualizationSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._06_visualization.task import (
    AINDEPhysVisualizationTask,
)
from obi_one.scientific.tasks.aind_ephys._07_results_collector.config import (
    AINDEPhysResultsCollectorSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._07_results_collector.task import (
    AINDEPhysResultsCollectorTask,
)
from obi_one.scientific.tasks.aind_ephys._08_processing_qc.config import (
    AINDEPhysProcessingQCSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._08_processing_qc.task import (
    AINDEPhysProcessingQCTask,
)
from obi_one.scientific.tasks.aind_ephys._09_qc_collector.config import (
    AINDEPhysQCCollectorSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._09_qc_collector.task import (
    AINDEPhysQCCollectorTask,
)
from obi_one.scientific.tasks.aind_ephys._10_ecephys_nwb.config import (
    AINDEcephysNWBSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._10_ecephys_nwb.task import (
    AINDEcephysNWBTask,
)
from obi_one.scientific.tasks.aind_ephys._11_units_nwb.config import (
    AINDUnitsNWBSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._11_units_nwb.task import (
    AINDUnitsNWBTask,
)
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
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit import (
    LearningEngineCircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (
    MEModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # noqa: E501
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

# Task registry: TaskType -> (task_cls, single_config_cls, asset_label)
# asset_label is None for tasks that receive their config inline.
TASK_MAP: dict[TaskType, tuple[type, type, AssetLabel | None]] = {
    # API-launchable tasks (submitted via the launch-system)
    TaskType.circuit_extraction: (
        CircuitExtractionTask,
        CircuitExtractionSingleConfig,
        AssetLabel.task_config,
    ),
    TaskType.circuit_simulation: (
        GenerateSimulationTask,
        CircuitSimulationSingleConfig,
        None,
    ),
    TaskType.em_synapse_mapping: (
        EMSynapseMappingTask,
        EMSynapseMappingSingleConfig,
        AssetLabel.task_config,
    ),
    TaskType.extracellular_recording_weights_calculation: (
        CreateExtracellularRecordingArrayTask,
        CreateExtracellularRecordingArraySingleConfig,
        AssetLabel.task_config,
    ),
    TaskType.ion_channel_model_simulation_execution: (
        IonChannelModelSimulationExecutionTask,
        IonChannelModelSimulationExecutionSingleConfig,
        None,
    ),
    TaskType.morphology_skeletonization: (
        SkeletonizationTask,
        SkeletonizationSingleConfig,
        AssetLabel.task_config,
    ),
    # Local-only tasks (executed via scan generation / direct dispatch)
    TaskType.basic_connectivity_plots: (
        BasicConnectivityPlotsTask,
        BasicConnectivityPlotsSingleConfig,
        None,
    ),
    TaskType.brian2_circuit_simulation: (
        GenerateSimulationTask,
        Brian2CircuitSimulationSingleConfig,
        None,
    ),
    TaskType.connectivity_matrix_extraction: (
        ConnectivityMatrixExtractionTask,
        ConnectivityMatrixExtractionSingleConfig,
        None,
    ),
    TaskType.contribute_morphology: (
        ContributeMorphologyTask,
        ContributeMorphologySingleConfig,
        None,
    ),
    TaskType.electrophysiology_metrics: (
        ElectrophysiologyMetricsTask,
        ElectrophysiologyMetricsSingleConfig,
        None,
    ),
    TaskType.folder_compression: (
        FolderCompressionTask,
        FolderCompressionSingleConfig,
        None,
    ),
    TaskType.ion_channel_fitting: (
        IonChannelFittingTask,
        IonChannelFittingSingleConfig,
        None,
    ),
    TaskType.ion_channel_model_simulation: (
        GenerateSimulationTask,
        IonChannelModelSimulationSingleConfig,
        None,
    ),
    TaskType.me_model_simulation: (
        GenerateSimulationTask,
        MEModelSimulationSingleConfig,
        None,
    ),
    TaskType.learning_engine_circuit_simulation: (
        GenerateSimulationTask,
        LearningEngineCircuitSimulationSingleConfig,
        None,
    ),
    TaskType.me_model_with_synapses_circuit_simulation: (
        GenerateSimulationTask,
        MEModelWithSynapsesCircuitSimulationSingleConfig,
        None,
    ),
    TaskType.morphology_containerization: (
        MorphologyContainerizationTask,
        MorphologyContainerizationSingleConfig,
        None,
    ),
    TaskType.morphology_decontainerization: (
        MorphologyDecontainerizationTask,
        MorphologyDecontainerizationSingleConfig,
        None,
    ),
    TaskType.morphology_locations: (
        MorphologyLocationsTask,
        MorphologyLocationsSingleConfig,
        None,
    ),
    TaskType.morphology_metrics: (
        MorphologyMetricsTask,
        MorphologyMetricsSingleConfig,
        None,
    ),
    TaskType.aind_ephys_preprocessing: (
        AINDEPhysPreprocessingTask,
        AINDEPhysPreprocessingSingleConfig,
        AssetLabel.task_config,
    ),
    TaskType.aind_ephys_spikesorting: (
        AINDEPhysSpikesortKilosort4Task,
        AINDEPhysSpikesortKilosort4SingleConfig,
        AssetLabel.task_config,
    ),
    TaskType.aind_ephys_postprocessing: (
        AINDEPhysPostprocessingTask,
        AINDEPhysPostprocessingSingleConfig,
        None,
    ),
    TaskType.aind_ephys_curation: (
        AINDEPhysCurationTask,
        AINDEPhysCurationSingleConfig,
        None,
    ),
    TaskType.aind_ephys_visualization: (
        AINDEPhysVisualizationTask,
        AINDEPhysVisualizationSingleConfig,
        None,
    ),
    TaskType.aind_ephys_results_collector: (
        AINDEPhysResultsCollectorTask,
        AINDEPhysResultsCollectorSingleConfig,
        None,
    ),
    TaskType.aind_ephys_processing_qc: (
        AINDEPhysProcessingQCTask,
        AINDEPhysProcessingQCSingleConfig,
        None,
    ),
    TaskType.aind_ephys_qc_collector: (
        AINDEPhysQCCollectorTask,
        AINDEPhysQCCollectorSingleConfig,
        None,
    ),
    TaskType.aind_ephys_cephys_nwb: (
        AINDEcephysNWBTask,
        AINDEcephysNWBSingleConfig,
        None,
    ),
    TaskType.aind_ephys_units_nwb: (
        AINDUnitsNWBTask,
        AINDUnitsNWBSingleConfig,
        None,
    ),
}

# Populate the registry from the static map
for task_type, (task_cls, single_config_cls, asset_label) in TASK_MAP.items():
    task_registry.register_task(
        task_type=task_type,
        task_cls=task_cls,
        single_config_cls=single_config_cls,
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

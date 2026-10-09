"""Declarative per-TaskType task specs.

Every class is declared as a ``(module path, class name)`` reference, so importing this
module imports no task implementation: the class is imported by the ``TaskSpec``
property that needs it. ``TASK_SPECS`` is the single place a task type is paired with
its task, SingleConfig and ScanConfig classes; ``core.deserializable_types`` derives
the deserialization type map from it.
"""

from importlib.util import find_spec

from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

from obi_one.core.registry import TaskSpec
from obi_one.types import TaskType
from obi_one.utils.lazy_import import class_name

# Module paths shared by several specs below, extracted so each class reference fits on
# one line. ``_GENERATE_SIMULATION_TASK_REF`` is a full reference, reused by every task
# type that dispatches to ``GenerateSimulationTask``.
_TASKS = "obi_one.scientific.tasks"
_NEURON_CONFIG = f"{_TASKS}.generate_simulations.config.neuron"
_SIMULATION_EXECUTION = f"{_TASKS}.simulation_execution.neuron"
_EMODEL_BUILDING = f"{_TASKS}.emodel_building"
_GENERATE_SIMULATION_TASK_REF = (
    f"{_TASKS}.generate_simulations.task.task",
    "GenerateSimulationTask",
)

TASK_SPECS: dict[TaskType, TaskSpec] = {
    TaskType.circuit_extraction: TaskSpec(
        task_ref=(f"{_TASKS}.circuit_extraction", "CircuitExtractionTask"),
        single_config_ref=(f"{_TASKS}.circuit_extraction", "CircuitExtractionSingleConfig"),
        scan_config_ref=(f"{_TASKS}.circuit_extraction", "CircuitExtractionScanConfig"),
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.circuit_extraction__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.circuit_extraction__config_generation
        ),
        single_task_config_type=TaskConfigType.circuit_extraction__config,
        single_task_activity_type=TaskActivityType.circuit_extraction__execution,
    ),
    TaskType.circuit_simulation: TaskSpec(
        task_ref=_GENERATE_SIMULATION_TASK_REF,
        single_config_ref=(f"{_NEURON_CONFIG}.neuron_circuit", "CircuitSimulationSingleConfig"),
        scan_config_ref=(f"{_NEURON_CONFIG}.neuron_circuit", "CircuitSimulationScanConfig"),
        asset_label=None,
    ),
    TaskType.circuit_synaptic_physiology_assignment: TaskSpec(
        task_ref=(f"{_TASKS}.synapse_parameterization.task", "SynapseParameterizationTask"),
        single_config_ref=(
            f"{_TASKS}.synapse_parameterization.config",
            "SynapseParameterizationSingleConfig",
        ),
        scan_config_ref=(
            f"{_TASKS}.synapse_parameterization.config",
            "SynapseParameterizationScanConfig",
        ),
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
    TaskType.em_synapse_mapping: TaskSpec(
        task_ref=(f"{_TASKS}.em_synapse_mapping.task", "EMSynapseMappingTask"),
        single_config_ref=(f"{_TASKS}.em_synapse_mapping.config", "EMSynapseMappingSingleConfig"),
        scan_config_ref=(f"{_TASKS}.em_synapse_mapping.config", "EMSynapseMappingScanConfig"),
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.em_synapse_mapping__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.em_synapse_mapping__config_generation
        ),
        single_task_config_type=TaskConfigType.em_synapse_mapping__config,
        single_task_activity_type=TaskActivityType.em_synapse_mapping__execution,
    ),
    TaskType.efeature_extraction: TaskSpec(
        task_ref=(
            f"{_EMODEL_BUILDING}.task1_efeature_extraction.task",
            "EModelEFeatureExtractionTask",
        ),
        single_config_ref=(
            f"{_EMODEL_BUILDING}.task1_efeature_extraction.config",
            "EModelEFeatureExtractionSingleConfig",
        ),
        scan_config_ref=(
            f"{_EMODEL_BUILDING}.task1_efeature_extraction.config",
            "EModelEFeatureExtractionScanConfig",
        ),
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.efeature_extraction__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.efeature_extraction__config_generation
        ),
        single_task_config_type=TaskConfigType.efeature_extraction__config,
        single_task_activity_type=TaskActivityType.efeature_extraction__execution,
    ),
    TaskType.extracellular_recording_weights_calculation: TaskSpec(
        task_ref=(
            f"{_TASKS}.create_recording_array.create_recording_array",
            "CreateExtracellularRecordingArrayTask",
        ),
        single_config_ref=(
            f"{_TASKS}.create_recording_array.create_recording_array",
            "CreateExtracellularRecordingArraySingleConfig",
        ),
        scan_config_ref=(
            f"{_TASKS}.create_recording_array.create_recording_array",
            "CreateExtracellularRecordingArrayScanConfig",
        ),
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
    TaskType.ion_channel_model_simulation_execution: TaskSpec(
        task_ref=(
            f"{_SIMULATION_EXECUTION}.ion_channel_simulation_execution",
            "IonChannelModelSimulationExecutionTask",
        ),
        single_config_ref=(
            f"{_SIMULATION_EXECUTION}.ion_channel_simulation_execution",
            "IonChannelModelSimulationExecutionSingleConfig",
        ),
        asset_label=None,
    ),
    TaskType.single_neuron_simulation_execution: TaskSpec(
        task_ref=(
            f"{_SIMULATION_EXECUTION}.single_neuron_simulation_execution",
            "SingleNeuronSimulationExecutionTask",
        ),
        single_config_ref=(
            f"{_SIMULATION_EXECUTION}.single_neuron_simulation_execution",
            "SingleNeuronSimulationExecutionSingleConfig",
        ),
        asset_label=None,
    ),
    TaskType.single_neuron_synaptome_simulation_execution: TaskSpec(
        task_ref=(
            f"{_SIMULATION_EXECUTION}.single_neuron_synaptome_simulation_execution",
            "SingleNeuronSynaptomeSimulationExecutionTask",
        ),
        single_config_ref=(
            f"{_SIMULATION_EXECUTION}.single_neuron_synaptome_simulation_execution",
            "SingleNeuronSynaptomeSimulationExecutionSingleConfig",
        ),
        asset_label=None,
    ),
    TaskType.mesh_lod_generation: TaskSpec(
        task_ref=(f"{_TASKS}.mesh_lod_generation.task", "MeshLODGenerationTask"),
        single_config_ref=(f"{_TASKS}.mesh_lod_generation.config", "MeshLodGenerationSingleConfig"),
        asset_label=AssetLabel.task_config,
        single_task_config_type=TaskConfigType.mesh_lod_generation__config,
        single_task_activity_type=TaskActivityType.mesh_lod_generation__execution,
    ),
    TaskType.morphology_skeletonization: TaskSpec(
        task_ref=(f"{_TASKS}.skeletonization", "SkeletonizationTask"),
        single_config_ref=(f"{_TASKS}.skeletonization", "SkeletonizationSingleConfig"),
        scan_config_ref=(f"{_TASKS}.skeletonization", "SkeletonizationScanConfig"),
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.skeletonization__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.skeletonization__config_generation
        ),
        single_task_config_type=TaskConfigType.skeletonization__config,
        single_task_activity_type=TaskActivityType.skeletonization__execution,
    ),
    TaskType.basic_connectivity_plots: TaskSpec(
        task_ref=(f"{_TASKS}.basic_connectivity_plots", "BasicConnectivityPlotsTask"),
        single_config_ref=(
            f"{_TASKS}.basic_connectivity_plots",
            "BasicConnectivityPlotsSingleConfig",
        ),
        scan_config_ref=(f"{_TASKS}.basic_connectivity_plots", "BasicConnectivityPlotsScanConfig"),
        asset_label=None,
    ),
    TaskType.brian2_circuit_simulation: TaskSpec(
        task_ref=_GENERATE_SIMULATION_TASK_REF,
        single_config_ref=(
            f"{_TASKS}.generate_simulations.config.brian2.brian2_circuit",
            "Brian2CircuitSimulationSingleConfig",
        ),
        scan_config_ref=(
            f"{_TASKS}.generate_simulations.config.brian2.brian2_circuit",
            "Brian2CircuitSimulationScanConfig",
        ),
        asset_label=None,
    ),
    TaskType.connectivity_matrix_extraction: TaskSpec(
        task_ref=(f"{_TASKS}.connectivity_matrix_extraction", "ConnectivityMatrixExtractionTask"),
        single_config_ref=(
            f"{_TASKS}.connectivity_matrix_extraction",
            "ConnectivityMatrixExtractionSingleConfig",
        ),
        scan_config_ref=(
            f"{_TASKS}.connectivity_matrix_extraction",
            "ConnectivityMatrixExtractionScanConfig",
        ),
        asset_label=None,
    ),
    TaskType.electrophysiology_metrics: TaskSpec(
        task_ref=(f"{_TASKS}.ephys_extraction", "ElectrophysiologyMetricsTask"),
        single_config_ref=(f"{_TASKS}.ephys_extraction", "ElectrophysiologyMetricsSingleConfig"),
        scan_config_ref=(f"{_TASKS}.ephys_extraction", "ElectrophysiologyMetricsScanConfig"),
        asset_label=None,
    ),
    TaskType.folder_compression: TaskSpec(
        task_ref=(f"{_TASKS}.folder_compression", "FolderCompressionTask"),
        single_config_ref=(f"{_TASKS}.folder_compression", "FolderCompressionSingleConfig"),
        scan_config_ref=(f"{_TASKS}.folder_compression", "FolderCompressionScanConfig"),
        asset_label=None,
    ),
    TaskType.ion_channel_fitting: TaskSpec(
        task_ref=(f"{_TASKS}.ion_channel_modeling", "IonChannelFittingTask"),
        single_config_ref=(f"{_TASKS}.ion_channel_modeling", "IonChannelFittingSingleConfig"),
        scan_config_ref=(f"{_TASKS}.ion_channel_modeling", "IonChannelFittingScanConfig"),
        asset_label=None,
    ),
    TaskType.ion_channel_model_simulation: TaskSpec(
        task_ref=_GENERATE_SIMULATION_TASK_REF,
        single_config_ref=(
            f"{_NEURON_CONFIG}.neuron_ion_channel_models",
            "IonChannelModelSimulationSingleConfig",
        ),
        scan_config_ref=(
            f"{_NEURON_CONFIG}.neuron_ion_channel_models",
            "IonChannelModelSimulationScanConfig",
        ),
        asset_label=None,
    ),
    TaskType.me_model_simulation: TaskSpec(
        task_ref=_GENERATE_SIMULATION_TASK_REF,
        single_config_ref=(f"{_NEURON_CONFIG}.neuron_me_model", "MEModelSimulationSingleConfig"),
        scan_config_ref=(f"{_NEURON_CONFIG}.neuron_me_model", "MEModelSimulationScanConfig"),
        asset_label=None,
    ),
    TaskType.learning_engine_circuit_simulation: TaskSpec(
        task_ref=_GENERATE_SIMULATION_TASK_REF,
        single_config_ref=(
            f"{_TASKS}.generate_simulations.config.learning_engine.le_circuit",
            "LearningEngineCircuitSimulationSingleConfig",
        ),
        scan_config_ref=(
            f"{_TASKS}.generate_simulations.config.learning_engine.le_circuit",
            "LearningEngineCircuitSimulationScanConfig",
        ),
        asset_label=None,
    ),
    TaskType.me_model_with_synapses_circuit_simulation: TaskSpec(
        task_ref=_GENERATE_SIMULATION_TASK_REF,
        single_config_ref=(
            f"{_NEURON_CONFIG}.neuron_me_model_with_synapses",
            "MEModelWithSynapsesCircuitSimulationSingleConfig",
        ),
        scan_config_ref=(
            f"{_NEURON_CONFIG}.neuron_me_model_with_synapses",
            "MEModelWithSynapsesCircuitSimulationScanConfig",
        ),
        asset_label=None,
    ),
    TaskType.morphology_containerization: TaskSpec(
        task_ref=(f"{_TASKS}.morphology_containerization", "MorphologyContainerizationTask"),
        single_config_ref=(
            f"{_TASKS}.morphology_containerization",
            "MorphologyContainerizationSingleConfig",
        ),
        scan_config_ref=(
            f"{_TASKS}.morphology_containerization",
            "MorphologyContainerizationScanConfig",
        ),
        asset_label=None,
    ),
    TaskType.morphology_decontainerization: TaskSpec(
        task_ref=(f"{_TASKS}.morphology_decontainerization", "MorphologyDecontainerizationTask"),
        single_config_ref=(
            f"{_TASKS}.morphology_decontainerization",
            "MorphologyDecontainerizationSingleConfig",
        ),
        scan_config_ref=(
            f"{_TASKS}.morphology_decontainerization",
            "MorphologyDecontainerizationScanConfig",
        ),
        asset_label=None,
    ),
    TaskType.morphology_locations: TaskSpec(
        task_ref=(f"{_TASKS}.morphology_locations", "MorphologyLocationsTask"),
        single_config_ref=(f"{_TASKS}.morphology_locations", "MorphologyLocationsSingleConfig"),
        scan_config_ref=(f"{_TASKS}.morphology_locations", "MorphologyLocationsScanConfig"),
        asset_label=None,
    ),
    TaskType.morphology_metrics: TaskSpec(
        task_ref=(f"{_TASKS}.morphology_metrics", "MorphologyMetricsTask"),
        single_config_ref=(f"{_TASKS}.morphology_metrics", "MorphologyMetricsSingleConfig"),
        scan_config_ref=(f"{_TASKS}.morphology_metrics", "MorphologyMetricsScanConfig"),
        asset_label=None,
    ),
    TaskType.circuit_simulation_neurodamus_machine: TaskSpec(
        task_ref=(
            f"{_SIMULATION_EXECUTION}.circuit_simulation_execution",
            "CircuitSimulationExecutionTask",
        ),
        single_config_ref=(
            f"{_SIMULATION_EXECUTION}.circuit_simulation_execution",
            "CircuitSimulationExecutionSingleConfig",
        ),
        asset_label=None,
    ),
    TaskType.circuit_single_build: TaskSpec(
        task_ref=(f"{_TASKS}.build_synaptome", "MEModelSynapticModelPlacementTask"),
        single_config_ref=(
            f"{_TASKS}.build_synaptome",
            "MEModelSynapticModelPlacementSingleConfig",
        ),
        scan_config_ref=(f"{_TASKS}.build_synaptome", "MEModelSynapticModelPlacementScanConfig"),
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.circuit_single_build__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.circuit_single_build__config_generation
        ),
        single_task_config_type=TaskConfigType.circuit_single_build__config,
        single_task_activity_type=TaskActivityType.circuit_single_build__execution,
    ),
    TaskType.emodel_optimization: TaskSpec(
        task_ref=(f"{_EMODEL_BUILDING}.task2_emodel_optimization.task", "EModelOptimizationTask"),
        single_config_ref=(
            f"{_EMODEL_BUILDING}.task2_emodel_optimization.config",
            "EModelOptimizationSingleConfig",
        ),
        scan_config_ref=(
            f"{_EMODEL_BUILDING}.task2_emodel_optimization.config",
            "EModelOptimizationScanConfig",
        ),
        asset_label=AssetLabel.task_config,
        campaign_task_config_type=TaskConfigType.emodel_optimization__campaign,
        campaign_generation_task_activity_type=(
            TaskActivityType.emodel_optimization__config_generation
        ),
        single_task_config_type=TaskConfigType.emodel_optimization__config,
        single_task_activity_type=TaskActivityType.emodel_optimization__execution,
        requires_package="bluepyemodel",
    ),
}


def _build_name_index(
    task_specs: dict[TaskType, TaskSpec],
    ref_attribute: str,
) -> dict[str, TaskType]:
    """Index task types by the class name declared in ``ref_attribute``.

    Class names are the ``type`` discriminator values of the config classes, so the
    index is built without importing any task module.
    """
    index: dict[str, TaskType] = {}
    for task_type, task_spec in task_specs.items():
        class_ref = getattr(task_spec, ref_attribute)
        if class_ref is None:
            continue
        index[class_name(class_ref)] = task_type
    return index


_SINGLE_CONFIG_NAME_INDEX: dict[str, TaskType] = _build_name_index(TASK_SPECS, "single_config_ref")
_SCAN_CONFIG_NAME_INDEX: dict[str, TaskType] = _build_name_index(TASK_SPECS, "scan_config_ref")


def _is_package_installed(package: str) -> bool:
    """Return whether ``package`` can be located without importing it.

    A package that cannot even be located (``ImportError`` from the import machinery)
    counts as not installed, which is the answer this probe exists to give.
    """
    try:
        return find_spec(package) is not None
    except ImportError:
        return False


def _is_task_type_available(task_type: TaskType) -> bool:
    """Return whether ``task_type`` has a spec whose optional dependency is installed."""
    task_spec = TASK_SPECS.get(task_type)
    if task_spec is None:
        return False
    return task_spec.requires_package is None or _is_package_installed(task_spec.requires_package)


def get_task_spec_for_task_type(task_type: TaskType) -> TaskSpec:
    """Return the task spec for ``task_type`` without importing the task's classes."""
    if not _is_task_type_available(task_type):
        msg = f"No task spec for {task_type!r}"
        raise KeyError(msg)
    return TASK_SPECS[task_type]


def _lookup_task_spec(index: dict[str, TaskType], config_cls: type) -> TaskSpec | None:
    """Return the task spec for a config class or the nearest registered base class.

    ``index`` is keyed by class name, which is the ``type`` discriminator value, so a
    config class is matched without importing the task module that defines it.
    """
    for klass in config_cls.__mro__:
        task_type = index.get(klass.__qualname__)
        if task_type is not None and _is_task_type_available(task_type):
            return TASK_SPECS[task_type]
    return None


def get_task_spec_for_scan_config(config_cls: type) -> TaskSpec | None:
    """Return the task spec for a ScanConfig class, or None if it has none."""
    return _lookup_task_spec(_SCAN_CONFIG_NAME_INDEX, config_cls)


def get_task_spec_for_single_config(config_cls: type) -> TaskSpec | None:
    """Return the task spec for a SingleConfig class, or None if it has none."""
    return _lookup_task_spec(_SINGLE_CONFIG_NAME_INDEX, config_cls)

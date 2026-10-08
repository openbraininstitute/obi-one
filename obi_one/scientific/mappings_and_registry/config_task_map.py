"""Per-TaskType task specs with match/case and lazy imports.

Importing this module does not load task implementations. Call
``get_task_spec_for_task_type`` for the task types you need.
"""

# ruff: file-ignore[import-outside-top-level, complex-structure, too-many-branches, too-many-statements]

from entitysdk.types import AssetLabel, TaskActivityType, TaskConfigType

from obi_one.core.registry import TaskSpec
from obi_one.types import TaskType

_CACHE: dict[TaskType, TaskSpec] = {}
_BY_SINGLE_CONFIG_CLS: dict[type, TaskSpec] = {}
_BY_SCAN_CONFIG_CLS: dict[type, TaskSpec] = {}


def _lookup_task_spec(index: dict[type, TaskSpec], config_cls: type) -> TaskSpec | None:
    """Return the task spec for a config class, walking the MRO."""
    for klass in config_cls.__mro__:
        task_spec = index.get(klass)
        if task_spec is not None:
            return task_spec
    return None


def _store_task_spec(task_type: TaskType, task_spec: TaskSpec) -> None:
    _CACHE[task_type] = task_spec
    _BY_SINGLE_CONFIG_CLS[task_spec.single_config_cls] = task_spec
    if task_spec.scan_config_cls is not None:
        _BY_SCAN_CONFIG_CLS[task_spec.scan_config_cls] = task_spec


def get_task_spec_for_scan_config(config_cls: type) -> TaskSpec | None:
    """Return the task spec for a ScanConfig class, resolving lazily when needed."""
    task_spec = _lookup_task_spec(_BY_SCAN_CONFIG_CLS, config_cls)
    if task_spec is not None:
        return task_spec
    task_type = getattr(config_cls, "task_type", None)
    if task_type is None:
        return None
    try:
        return get_task_spec_for_task_type(task_type)
    except KeyError:
        return None


def get_task_spec_for_single_config(config_cls: type) -> TaskSpec | None:
    """Return the task spec for a SingleConfig class, resolving lazily when needed."""
    task_spec = _lookup_task_spec(_BY_SINGLE_CONFIG_CLS, config_cls)
    if task_spec is not None:
        return task_spec
    task_type = getattr(config_cls, "task_type", None)
    if task_type is None:
        return None
    try:
        return get_task_spec_for_task_type(task_type)
    except KeyError:
        return None


def is_task_type_resolved(task_type: TaskType) -> bool:
    """Return whether ``task_type`` is already in the task spec cache.

    Does not import task implementations; use ``get_task_spec_for_task_type`` to
    load and register a type.
    """
    return task_type in _CACHE


def get_task_spec_for_task_type(task_type: TaskType) -> TaskSpec:
    """Return the task spec for ``task_type``, importing that task only if needed."""
    if task_type in _CACHE:
        return _CACHE[task_type]

    match task_type:
        case TaskType.circuit_extraction:
            from obi_one.scientific.tasks.circuit_extraction import (
                CircuitExtractionScanConfig,
                CircuitExtractionSingleConfig,
                CircuitExtractionTask,
            )

            task_spec = TaskSpec(
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
            )

        case TaskType.circuit_simulation:
            from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
                CircuitSimulationScanConfig,
                CircuitSimulationSingleConfig,
            )
            from obi_one.scientific.tasks.generate_simulations.task.task import (
                GenerateSimulationTask,
            )

            task_spec = TaskSpec(
                task_cls=GenerateSimulationTask,
                single_config_cls=CircuitSimulationSingleConfig,
                scan_config_cls=CircuitSimulationScanConfig,
                asset_label=None,
            )

        case TaskType.circuit_synaptic_physiology_assignment:
            from obi_one.scientific.tasks.synapse_parameterization.config import (
                SynapseParameterizationScanConfig,
                SynapseParameterizationSingleConfig,
            )
            from obi_one.scientific.tasks.synapse_parameterization.task import (
                SynapseParameterizationTask,
            )

            task_spec = TaskSpec(
                task_cls=SynapseParameterizationTask,
                single_config_cls=SynapseParameterizationSingleConfig,
                scan_config_cls=SynapseParameterizationScanConfig,
                asset_label=AssetLabel.task_config,
                campaign_task_config_type=(
                    TaskConfigType.circuit_synaptic_physiology_assignment__campaign
                ),
                campaign_generation_task_activity_type=(
                    TaskActivityType.circuit_synaptic_physiology_assignment__config_generation
                ),
                single_task_config_type=(
                    TaskConfigType.circuit_synaptic_physiology_assignment__config
                ),
                single_task_activity_type=(
                    TaskActivityType.circuit_synaptic_physiology_assignment__execution
                ),
            )

        case TaskType.em_synapse_mapping:
            from obi_one.scientific.tasks.em_synapse_mapping.config import (
                EMSynapseMappingScanConfig,
                EMSynapseMappingSingleConfig,
            )
            from obi_one.scientific.tasks.em_synapse_mapping.task import EMSynapseMappingTask

            task_spec = TaskSpec(
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
            )

        case TaskType.efeature_extraction:
            from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.config import (
                EModelEFeatureExtractionScanConfig,
                EModelEFeatureExtractionSingleConfig,
            )
            from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
                EModelEFeatureExtractionTask,
            )

            task_spec = TaskSpec(
                task_cls=EModelEFeatureExtractionTask,
                single_config_cls=EModelEFeatureExtractionSingleConfig,
                scan_config_cls=EModelEFeatureExtractionScanConfig,
                asset_label=AssetLabel.task_config,
                campaign_task_config_type=TaskConfigType.efeature_extraction__campaign,
                campaign_generation_task_activity_type=(
                    TaskActivityType.efeature_extraction__config_generation
                ),
                single_task_config_type=TaskConfigType.efeature_extraction__config,
                single_task_activity_type=TaskActivityType.efeature_extraction__execution,
            )

        case TaskType.extracellular_recording_weights_calculation:
            from obi_one.scientific.tasks.create_recording_array.create_recording_array import (
                CreateExtracellularRecordingArrayScanConfig,
                CreateExtracellularRecordingArraySingleConfig,
                CreateExtracellularRecordingArrayTask,
            )

            task_spec = TaskSpec(
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
                single_task_config_type=(
                    TaskConfigType.extracellular_recording_weights_calculation__config
                ),
                single_task_activity_type=(
                    TaskActivityType.extracellular_recording_weights_calculation__execution
                ),
            )

        case TaskType.ion_channel_model_simulation_execution:
            from obi_one.scientific.tasks.simulation_execution.neuron.ion_channel_simulation_execution import (  # ruff: ignore[line-too-long]
                IonChannelModelSimulationExecutionSingleConfig,
                IonChannelModelSimulationExecutionTask,
            )

            task_spec = TaskSpec(
                task_cls=IonChannelModelSimulationExecutionTask,
                single_config_cls=IonChannelModelSimulationExecutionSingleConfig,
                asset_label=None,
            )

        case TaskType.single_neuron_simulation_execution:
            from obi_one.scientific.tasks.simulation_execution.neuron.single_neuron_simulation_execution import (  # ruff: ignore[line-too-long]
                SingleNeuronSimulationExecutionSingleConfig,
                SingleNeuronSimulationExecutionTask,
            )

            task_spec = TaskSpec(
                task_cls=SingleNeuronSimulationExecutionTask,
                single_config_cls=SingleNeuronSimulationExecutionSingleConfig,
                asset_label=None,
            )

        case TaskType.single_neuron_synaptome_simulation_execution:
            from obi_one.scientific.tasks.simulation_execution.neuron.single_neuron_synaptome_simulation_execution import (  # ruff: ignore[line-too-long]
                SingleNeuronSynaptomeSimulationExecutionSingleConfig,
                SingleNeuronSynaptomeSimulationExecutionTask,
            )

            task_spec = TaskSpec(
                task_cls=SingleNeuronSynaptomeSimulationExecutionTask,
                single_config_cls=SingleNeuronSynaptomeSimulationExecutionSingleConfig,
                asset_label=None,
            )

        case TaskType.mesh_lod_generation:
            from obi_one.scientific.tasks.mesh_lod_generation.config import (
                MeshLodGenerationSingleConfig,
            )
            from obi_one.scientific.tasks.mesh_lod_generation.task import MeshLODGenerationTask

            task_spec = TaskSpec(
                task_cls=MeshLODGenerationTask,
                single_config_cls=MeshLodGenerationSingleConfig,
                asset_label=AssetLabel.task_config,
                single_task_config_type=TaskConfigType.mesh_lod_generation__config,
                single_task_activity_type=TaskActivityType.mesh_lod_generation__execution,
            )

        case TaskType.morphology_skeletonization:
            from obi_one.scientific.tasks.skeletonization import (
                SkeletonizationScanConfig,
                SkeletonizationSingleConfig,
                SkeletonizationTask,
            )

            task_spec = TaskSpec(
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
            )

        case TaskType.basic_connectivity_plots:
            from obi_one.scientific.tasks.basic_connectivity_plots import (
                BasicConnectivityPlotsScanConfig,
                BasicConnectivityPlotsSingleConfig,
                BasicConnectivityPlotsTask,
            )

            task_spec = TaskSpec(
                task_cls=BasicConnectivityPlotsTask,
                single_config_cls=BasicConnectivityPlotsSingleConfig,
                scan_config_cls=BasicConnectivityPlotsScanConfig,
                asset_label=None,
            )

        case TaskType.brian2_circuit_simulation:
            from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
                Brian2CircuitSimulationScanConfig,
                Brian2CircuitSimulationSingleConfig,
            )
            from obi_one.scientific.tasks.generate_simulations.task.task import (
                GenerateSimulationTask,
            )

            task_spec = TaskSpec(
                task_cls=GenerateSimulationTask,
                single_config_cls=Brian2CircuitSimulationSingleConfig,
                scan_config_cls=Brian2CircuitSimulationScanConfig,
                asset_label=None,
            )

        case TaskType.connectivity_matrix_extraction:
            from obi_one.scientific.tasks.connectivity_matrix_extraction import (
                ConnectivityMatrixExtractionScanConfig,
                ConnectivityMatrixExtractionSingleConfig,
                ConnectivityMatrixExtractionTask,
            )

            task_spec = TaskSpec(
                task_cls=ConnectivityMatrixExtractionTask,
                single_config_cls=ConnectivityMatrixExtractionSingleConfig,
                scan_config_cls=ConnectivityMatrixExtractionScanConfig,
                asset_label=None,
            )

        case TaskType.electrophysiology_metrics:
            from obi_one.scientific.tasks.ephys_extraction import (
                ElectrophysiologyMetricsScanConfig,
                ElectrophysiologyMetricsSingleConfig,
                ElectrophysiologyMetricsTask,
            )

            task_spec = TaskSpec(
                task_cls=ElectrophysiologyMetricsTask,
                single_config_cls=ElectrophysiologyMetricsSingleConfig,
                scan_config_cls=ElectrophysiologyMetricsScanConfig,
                asset_label=None,
            )

        case TaskType.folder_compression:
            from obi_one.scientific.tasks.folder_compression import (
                FolderCompressionScanConfig,
                FolderCompressionSingleConfig,
                FolderCompressionTask,
            )

            task_spec = TaskSpec(
                task_cls=FolderCompressionTask,
                single_config_cls=FolderCompressionSingleConfig,
                scan_config_cls=FolderCompressionScanConfig,
                asset_label=None,
            )

        case TaskType.ion_channel_fitting:
            from obi_one.scientific.tasks.ion_channel_modeling import (
                IonChannelFittingScanConfig,
                IonChannelFittingSingleConfig,
                IonChannelFittingTask,
            )

            task_spec = TaskSpec(
                task_cls=IonChannelFittingTask,
                single_config_cls=IonChannelFittingSingleConfig,
                scan_config_cls=IonChannelFittingScanConfig,
                asset_label=None,
            )

        case TaskType.ion_channel_model_simulation:
            from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (  # ruff: ignore[line-too-long]
                IonChannelModelSimulationScanConfig,
                IonChannelModelSimulationSingleConfig,
            )
            from obi_one.scientific.tasks.generate_simulations.task.task import (
                GenerateSimulationTask,
            )

            task_spec = TaskSpec(
                task_cls=GenerateSimulationTask,
                single_config_cls=IonChannelModelSimulationSingleConfig,
                scan_config_cls=IonChannelModelSimulationScanConfig,
                asset_label=None,
            )

        case TaskType.me_model_simulation:
            from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model import (  # ruff: ignore[line-too-long]
                MEModelSimulationScanConfig,
                MEModelSimulationSingleConfig,
            )
            from obi_one.scientific.tasks.generate_simulations.task.task import (
                GenerateSimulationTask,
            )

            task_spec = TaskSpec(
                task_cls=GenerateSimulationTask,
                single_config_cls=MEModelSimulationSingleConfig,
                scan_config_cls=MEModelSimulationScanConfig,
                asset_label=None,
            )

        case TaskType.learning_engine_circuit_simulation:
            from obi_one.scientific.tasks.generate_simulations.config.learning_engine.le_circuit import (  # ruff: ignore[line-too-long]
                LearningEngineCircuitSimulationScanConfig,
                LearningEngineCircuitSimulationSingleConfig,
            )
            from obi_one.scientific.tasks.generate_simulations.task.task import (
                GenerateSimulationTask,
            )

            task_spec = TaskSpec(
                task_cls=GenerateSimulationTask,
                single_config_cls=LearningEngineCircuitSimulationSingleConfig,
                scan_config_cls=LearningEngineCircuitSimulationScanConfig,
                asset_label=None,
            )

        case TaskType.me_model_with_synapses_circuit_simulation:
            from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_me_model_with_synapses import (  # ruff: ignore[line-too-long]
                MEModelWithSynapsesCircuitSimulationScanConfig,
                MEModelWithSynapsesCircuitSimulationSingleConfig,
            )
            from obi_one.scientific.tasks.generate_simulations.task.task import (
                GenerateSimulationTask,
            )

            task_spec = TaskSpec(
                task_cls=GenerateSimulationTask,
                single_config_cls=MEModelWithSynapsesCircuitSimulationSingleConfig,
                scan_config_cls=MEModelWithSynapsesCircuitSimulationScanConfig,
                asset_label=None,
            )

        case TaskType.morphology_containerization:
            from obi_one.scientific.tasks.morphology_containerization import (
                MorphologyContainerizationScanConfig,
                MorphologyContainerizationSingleConfig,
                MorphologyContainerizationTask,
            )

            task_spec = TaskSpec(
                task_cls=MorphologyContainerizationTask,
                single_config_cls=MorphologyContainerizationSingleConfig,
                scan_config_cls=MorphologyContainerizationScanConfig,
                asset_label=None,
            )

        case TaskType.morphology_decontainerization:
            from obi_one.scientific.tasks.morphology_decontainerization import (
                MorphologyDecontainerizationScanConfig,
                MorphologyDecontainerizationSingleConfig,
                MorphologyDecontainerizationTask,
            )

            task_spec = TaskSpec(
                task_cls=MorphologyDecontainerizationTask,
                single_config_cls=MorphologyDecontainerizationSingleConfig,
                scan_config_cls=MorphologyDecontainerizationScanConfig,
                asset_label=None,
            )

        case TaskType.morphology_locations:
            from obi_one.scientific.tasks.morphology_locations import (
                MorphologyLocationsScanConfig,
                MorphologyLocationsSingleConfig,
                MorphologyLocationsTask,
            )

            task_spec = TaskSpec(
                task_cls=MorphologyLocationsTask,
                single_config_cls=MorphologyLocationsSingleConfig,
                scan_config_cls=MorphologyLocationsScanConfig,
                asset_label=None,
            )

        case TaskType.morphology_metrics:
            from obi_one.scientific.tasks.morphology_metrics import (
                MorphologyMetricsScanConfig,
                MorphologyMetricsSingleConfig,
                MorphologyMetricsTask,
            )

            task_spec = TaskSpec(
                task_cls=MorphologyMetricsTask,
                single_config_cls=MorphologyMetricsSingleConfig,
                scan_config_cls=MorphologyMetricsScanConfig,
                asset_label=None,
            )

        case TaskType.circuit_simulation_neurodamus_machine:
            from obi_one.scientific.tasks.simulation_execution.neuron.circuit_simulation_execution import (  # ruff: ignore[line-too-long]
                CircuitSimulationExecutionSingleConfig,
                CircuitSimulationExecutionTask,
            )

            task_spec = TaskSpec(
                task_cls=CircuitSimulationExecutionTask,
                single_config_cls=CircuitSimulationExecutionSingleConfig,
                asset_label=None,
            )

        case TaskType.circuit_single_build:
            from obi_one.scientific.tasks.build_synaptome import (
                MEModelSynapticModelPlacementScanConfig,
                MEModelSynapticModelPlacementSingleConfig,
                MEModelSynapticModelPlacementTask,
            )

            task_spec = TaskSpec(
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
            )

        case TaskType.emodel_optimization:
            from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization import (
                HAS_EMODEL_OPTIMIZATION,
                EModelOptimizationScanConfig,
                EModelOptimizationSingleConfig,
                EModelOptimizationTask,
            )

            if not (
                HAS_EMODEL_OPTIMIZATION
                and EModelOptimizationTask is not None
                and EModelOptimizationSingleConfig is not None
                and EModelOptimizationScanConfig is not None
            ):
                msg = f"No task spec for {task_type!r}"
                raise KeyError(msg)

            task_spec = TaskSpec(
                task_cls=EModelOptimizationTask,
                single_config_cls=EModelOptimizationSingleConfig,
                scan_config_cls=EModelOptimizationScanConfig,
                asset_label=AssetLabel.task_config,
                campaign_task_config_type=TaskConfigType.emodel_optimization__campaign,
                campaign_generation_task_activity_type=(
                    TaskActivityType.emodel_optimization__config_generation
                ),
                single_task_config_type=TaskConfigType.emodel_optimization__config,
                single_task_activity_type=TaskActivityType.emodel_optimization__execution,
            )

        case _:
            msg = f"No task spec for {task_type!r}"
            raise KeyError(msg)

    _store_task_spec(task_type, task_spec)
    return task_spec

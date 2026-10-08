from unittest.mock import MagicMock

import pytest
from entitysdk.types import AssetLabel

from obi_one.core import run_tasks
from obi_one.core.base import OBIBaseModel
from obi_one.core.task import Task
from obi_one.scientific.mappings_and_registry import config_task_map as test_module
from obi_one.scientific.tasks.build_synaptome import (
    MEModelSynapticModelPlacementSingleConfig,
    MEModelSynapticModelPlacementTask,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionScanConfig,
    CircuitExtractionSingleConfig,
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingScanConfig
from obi_one.scientific.tasks.generate_simulations.config.neuron.aliases import Simulation
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
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
from obi_one.types import TaskType

# Every ``case TaskType.…`` branch in ``config_task_map.get_task_spec_for_task_type``.
CONFIG_TASK_MAP_CASES = (
    TaskType.circuit_extraction,
    TaskType.circuit_simulation,
    TaskType.circuit_synaptic_physiology_assignment,
    TaskType.em_synapse_mapping,
    TaskType.efeature_extraction,
    TaskType.extracellular_recording_weights_calculation,
    TaskType.ion_channel_model_simulation_execution,
    TaskType.single_neuron_simulation_execution,
    TaskType.single_neuron_synaptome_simulation_execution,
    TaskType.mesh_lod_generation,
    TaskType.morphology_skeletonization,
    TaskType.basic_connectivity_plots,
    TaskType.brian2_circuit_simulation,
    TaskType.connectivity_matrix_extraction,
    TaskType.electrophysiology_metrics,
    TaskType.folder_compression,
    TaskType.ion_channel_fitting,
    TaskType.ion_channel_model_simulation,
    TaskType.me_model_simulation,
    TaskType.learning_engine_circuit_simulation,
    TaskType.me_model_with_synapses_circuit_simulation,
    TaskType.morphology_containerization,
    TaskType.morphology_decontainerization,
    TaskType.morphology_locations,
    TaskType.morphology_metrics,
    TaskType.circuit_simulation_neurodamus_machine,
    TaskType.circuit_single_build,
    TaskType.emodel_optimization,
)

# Launch-system task types that are not registered in ``config_task_map``.
LAUNCH_SYSTEM_TASK_TYPES_WITHOUT_CONFIG_MAP = (
    TaskType.circuit_simulation_inait_machine,
    TaskType.circuit_simulation_neuron,
    TaskType.circuit_simulation_neurodamus_cluster,
    TaskType.circuit_simulation_brian2_machine,
)


def test_config_task_map_cases_partition_task_type_enum():
    mapped = set(CONFIG_TASK_MAP_CASES)
    unmapped = set(LAUNCH_SYSTEM_TASK_TYPES_WITHOUT_CONFIG_MAP)
    assert mapped.isdisjoint(unmapped)
    assert mapped | unmapped == set(TaskType)


@pytest.mark.parametrize("task_type", CONFIG_TASK_MAP_CASES)
def test_config_task_map_match_case_resolves(task_type: TaskType):
    task_spec = test_module.get_task_spec_for_task_type(task_type)

    assert issubclass(task_spec.task_cls, Task)
    assert issubclass(task_spec.single_config_cls, OBIBaseModel)
    assert getattr(task_spec.single_config_cls, "task_type", None) is task_type

    assert test_module.get_task_spec_for_single_config(task_spec.single_config_cls) is task_spec

    if task_spec.scan_config_cls is not None:
        assert getattr(task_spec.scan_config_cls, "task_type", None) is task_type
        assert test_module.get_task_spec_for_scan_config(task_spec.scan_config_cls) is task_spec


@pytest.mark.parametrize("task_type", LAUNCH_SYSTEM_TASK_TYPES_WITHOUT_CONFIG_MAP)
def test_config_task_map_unregistered_task_type_raises(task_type: TaskType):
    with pytest.raises(KeyError, match="No task spec"):
        test_module.get_task_spec_for_task_type(task_type)


@pytest.mark.parametrize(
    ("task_type", "task_class"),
    [
        (TaskType.circuit_extraction, CircuitExtractionTask),
        (
            TaskType.ion_channel_model_simulation_execution,
            IonChannelModelSimulationExecutionTask,
        ),
        (
            TaskType.single_neuron_simulation_execution,
            SingleNeuronSimulationExecutionTask,
        ),
        (
            TaskType.single_neuron_synaptome_simulation_execution,
            SingleNeuronSynaptomeSimulationExecutionTask,
        ),
        (
            TaskType.circuit_simulation_neurodamus_machine,
            CircuitSimulationExecutionTask,
        ),
        (TaskType.morphology_skeletonization, SkeletonizationTask),
        (TaskType.circuit_single_build, MEModelSynapticModelPlacementTask),
    ],
)
def test_get_task_spec_for_task_type_task_cls(task_type, task_class):
    assert test_module.get_task_spec_for_task_type(task_type).task_cls is task_class


@pytest.mark.parametrize(
    ("task_type", "single_config_class"),
    [
        (TaskType.circuit_extraction, CircuitExtractionSingleConfig),
        (
            TaskType.ion_channel_model_simulation_execution,
            IonChannelModelSimulationExecutionSingleConfig,
        ),
        (
            TaskType.single_neuron_simulation_execution,
            SingleNeuronSimulationExecutionSingleConfig,
        ),
        (
            TaskType.single_neuron_synaptome_simulation_execution,
            SingleNeuronSynaptomeSimulationExecutionSingleConfig,
        ),
        (
            TaskType.circuit_simulation_neurodamus_machine,
            CircuitSimulationExecutionSingleConfig,
        ),
        (TaskType.morphology_skeletonization, SkeletonizationSingleConfig),
        (TaskType.circuit_single_build, MEModelSynapticModelPlacementSingleConfig),
    ],
)
def test_get_task_spec_for_task_type_single_config_cls(task_type, single_config_class):
    assert (
        test_module.get_task_spec_for_task_type(task_type).single_config_cls is single_config_class
    )


@pytest.mark.parametrize(
    ("task_type", "asset_label"),
    [
        (TaskType.circuit_extraction, AssetLabel.task_config),
        (TaskType.morphology_skeletonization, AssetLabel.task_config),
        (TaskType.circuit_single_build, AssetLabel.task_config),
        (TaskType.circuit_simulation, None),
        (TaskType.ion_channel_model_simulation_execution, None),
        (TaskType.single_neuron_simulation_execution, None),
        (TaskType.single_neuron_synaptome_simulation_execution, None),
        (TaskType.circuit_simulation_neurodamus_machine, None),
    ],
)
def test_get_task_spec_for_task_type_asset_label(task_type, asset_label):
    assert test_module.get_task_spec_for_task_type(task_type).asset_label is asset_label


@pytest.mark.parametrize(
    ("config_class", "task_class"),
    [
        (CircuitSimulationSingleConfig, GenerateSimulationTask),
        (CircuitExtractionSingleConfig, CircuitExtractionTask),
        (
            IonChannelModelSimulationSingleConfig,
            GenerateSimulationTask,
        ),
    ],
)
def test_get_task_spec_for_single_config_task_cls(config_class, task_class):
    task_spec = test_module.get_task_spec_for_single_config(config_class)
    assert task_spec is not None
    assert task_spec.task_cls is task_class


@pytest.mark.parametrize(
    "scan_config_class",
    [
        CircuitExtractionScanConfig,
        EMSynapseMappingScanConfig,
        SkeletonizationScanConfig,
    ],
)
def test_scan_config_does_not_dispatch_to_a_task(scan_config_class):
    """A ScanConfig may still hold multi-value parameters, so it is not executable."""
    config = MagicMock(spec=scan_config_class)
    with pytest.raises(KeyError, match="No task registered"):
        run_tasks.run_task_for_single_config(config)


def test_single_config_subclass_dispatches_via_its_base():
    """The Simulation alias subclasses CircuitSimulationSingleConfig without registering."""
    task_spec = test_module.get_task_spec_for_single_config(Simulation)
    assert task_spec is not None
    assert task_spec.task_cls is GenerateSimulationTask


def test_get_task_spec_for_task_type_caches():
    first = test_module.get_task_spec_for_task_type(TaskType.circuit_extraction)
    second = test_module.get_task_spec_for_task_type(TaskType.circuit_extraction)
    assert first is second

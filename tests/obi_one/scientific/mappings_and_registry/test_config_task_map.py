from unittest.mock import MagicMock

import pytest

from obi_one.scientific.mappings_and_registry import config_task_map as test_module
from obi_one.scientific.tasks.generate_simulations.config.neuron.aliases import Simulation
from obi_one.types import TaskType


@pytest.mark.parametrize(
    ("task_type", "task_class"),
    [
        (TaskType.circuit_extraction, test_module.CircuitExtractionTask),
        (
            TaskType.ion_channel_model_simulation_execution,
            test_module.IonChannelModelSimulationExecutionTask,
        ),
        (
            TaskType.single_neuron_simulation_execution,
            test_module.SingleNeuronSimulationExecutionTask,
        ),
        (
            TaskType.single_neuron_synaptome_simulation_execution,
            test_module.SingleNeuronSynaptomeSimulationExecutionTask,
        ),
        (
            TaskType.circuit_simulation_neurodamus_machine,
            test_module.CircuitSimulationExecutionTask,
        ),
        (TaskType.morphology_skeletonization, test_module.SkeletonizationTask),
        (TaskType.circuit_single_build, test_module.MEModelSynapticModelPlacementTask),
        (TaskType.me_model_synapse_placement, test_module.MEModelSynapticModelPlacementTask),
    ],
)
def test_get_task_type(task_type, task_class):
    res = test_module.get_task_type(task_type)
    assert res is task_class


@pytest.mark.parametrize(
    ("task_type", "single_config_class"),
    [
        (TaskType.circuit_extraction, test_module.CircuitExtractionSingleConfig),
        (
            TaskType.ion_channel_model_simulation_execution,
            test_module.IonChannelModelSimulationExecutionSingleConfig,
        ),
        (
            TaskType.single_neuron_simulation_execution,
            test_module.SingleNeuronSimulationExecutionSingleConfig,
        ),
        (
            TaskType.single_neuron_synaptome_simulation_execution,
            test_module.SingleNeuronSynaptomeSimulationExecutionSingleConfig,
        ),
        (
            TaskType.circuit_simulation_neurodamus_machine,
            test_module.CircuitSimulationExecutionSingleConfig,
        ),
        (TaskType.morphology_skeletonization, test_module.SkeletonizationSingleConfig),
        (TaskType.circuit_single_build, test_module.MEModelSynapticModelPlacementSingleConfig),
        (TaskType.me_model_synapse_placement, test_module.MEModelSynapticModelPlacementSingleConfig),
    ],
)
def test_get_task_type_single_config(task_type, single_config_class):
    res = test_module.get_task_type_single_config(task_type)
    assert res is single_config_class


@pytest.mark.parametrize(
    ("task_type", "asset_label"),
    [
        (TaskType.circuit_extraction, test_module.AssetLabel.task_config),
        (TaskType.morphology_skeletonization, test_module.AssetLabel.task_config),
        (TaskType.circuit_single_build, test_module.AssetLabel.task_config),
        (TaskType.circuit_simulation, None),
        (TaskType.ion_channel_model_simulation_execution, None),
        (TaskType.single_neuron_simulation_execution, None),
        (TaskType.single_neuron_synaptome_simulation_execution, None),
        (TaskType.circuit_simulation_neurodamus_machine, None),
    ],
)
def test_get_task_type_config_asset_label(task_type, asset_label):
    res = test_module.get_task_type_config_asset_label(task_type)
    assert res is asset_label


@pytest.mark.parametrize(
    ("config_class", "task_class"),
    [
        (test_module.CircuitSimulationSingleConfig, test_module.GenerateSimulationTask),
        (test_module.CircuitExtractionSingleConfig, test_module.CircuitExtractionTask),
        (
            test_module.IonChannelModelSimulationSingleConfig,
            test_module.GenerateSimulationTask,
        ),
    ],
)
def test_get_single_configs_task_type(config_class, task_class):
    config = MagicMock(spec=config_class)
    res = test_module.get_single_configs_task_type(config)
    assert res is task_class


@pytest.mark.parametrize(
    "scan_config_class",
    [
        test_module.CircuitExtractionScanConfig,
        test_module.EMSynapseMappingScanConfig,
        test_module.SkeletonizationScanConfig,
    ],
)
def test_scan_config_does_not_dispatch_to_a_task(scan_config_class):
    """A ScanConfig may still hold multi-value parameters, so it is not executable."""
    config = MagicMock(spec=scan_config_class)
    with pytest.raises(KeyError, match="No task registered"):
        test_module.get_single_configs_task_type(config)


def test_single_config_subclass_dispatches_via_its_base():
    """The Simulation alias subclasses CircuitSimulationSingleConfig without registering."""
    config = MagicMock(spec=Simulation)
    res = test_module.get_single_configs_task_type(config)
    assert res is test_module.GenerateSimulationTask

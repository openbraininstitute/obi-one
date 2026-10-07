from unittest.mock import MagicMock

import pytest
from entitysdk.types import AssetLabel

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
def test_get_task_type(task_type, task_class):
    res = test_module.get_task_type(task_type)
    assert res is task_class


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
def test_get_task_type_single_config(task_type, single_config_class):
    res = test_module.get_task_type_single_config(task_type)
    assert res is single_config_class


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
def test_get_task_type_config_asset_label(task_type, asset_label):
    res = test_module.get_task_type_config_asset_label(task_type)
    assert res is asset_label


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
def test_get_single_configs_task_type(config_class, task_class):
    config = MagicMock(spec=config_class)
    res = test_module.get_single_configs_task_type(config)
    assert res is task_class


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
        test_module.get_single_configs_task_type(config)


def test_single_config_subclass_dispatches_via_its_base():
    """The Simulation alias subclasses CircuitSimulationSingleConfig without registering."""
    config = MagicMock(spec=Simulation)
    res = test_module.get_single_configs_task_type(config)
    assert res is GenerateSimulationTask


def test_resolve_task_registration_caches():
    first = test_module.resolve_task_registration(TaskType.circuit_extraction)
    second = test_module.resolve_task_registration(TaskType.circuit_extraction)
    assert first is second

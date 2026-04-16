from unittest.mock import MagicMock

import pytest

from obi_one.scientific.unions import config_task_map as test_module
from obi_one.types import TaskType


@pytest.mark.parametrize(
    ("task_type", "task_class"),
    [
        (TaskType.circuit_extraction, test_module.CircuitExtractionTask),
        (
            TaskType.ion_channel_model_simulation_execution,
            test_module.IonChannelModelSimulationExecutionTask,
        ),
        (TaskType.morphology_skeletonization, test_module.SkeletonizationTask),
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
        (TaskType.morphology_skeletonization, test_module.SkeletonizationSingleConfig),
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
        (TaskType.circuit_simulation, None),
        (TaskType.ion_channel_model_simulation_execution, None),
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
def test_get_configs_task_type(config_class, task_class):
    config = MagicMock(spec=config_class)
    res = test_module.get_configs_task_type(config)
    assert res is task_class

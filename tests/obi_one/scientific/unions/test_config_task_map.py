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

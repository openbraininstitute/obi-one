from app.mappings import TASK_DEFINITIONS
from app.types import TaskType


def test_it_installs_the_builder_the_task_imports_behind_a_try_except():
    definition = TASK_DEFINITIONS[TaskType.ion_channel_fitting]

    assert definition.code.dependencies.endswith("ion_channel_fitting.txt")

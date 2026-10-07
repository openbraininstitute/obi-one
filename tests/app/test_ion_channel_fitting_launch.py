"""The launch wiring for ion channel fitting."""

from app.mappings import TASK_DEFINITIONS
from app.types import TaskType


def test_it_installs_the_builder_the_task_imports_behind_a_try_except():
    """obi-one does not depend on ion_channel_builder, so without this the task would run
    against its no-op stubs and register an empty model rather than failing.
    """
    definition = TASK_DEFINITIONS[TaskType.ion_channel_fitting]

    assert definition.code.dependencies.endswith("ion_channel_fitting.txt")

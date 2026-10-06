"""The launch wiring for ion channel fitting.

The fit itself needs `ion_channel_builder` and `nrnivmodl`, so these check the wiring that
decides whether it can be launched at all, not the science.
"""

from entitysdk.types import TaskActivityType, TaskConfigType

from app.mappings import TASK_DEFINITIONS
from app.types import MachineExecutorImageType, TaskType


def test_ion_channel_fitting_is_launchable():
    assert TaskType.ion_channel_fitting in TASK_DEFINITIONS


def test_it_launches_against_the_entities_the_scan_actually_registers():
    definition = TASK_DEFINITIONS[TaskType.ion_channel_fitting]

    assert definition.config_type == TaskConfigType.ion_channel_modeling__config
    assert definition.activity_type == TaskActivityType.ion_channel_modeling__execution


def test_it_asks_for_an_image_with_neuron():
    """The task compiles the generated mod file with nrnivmodl and then runs it."""
    definition = TASK_DEFINITIONS[TaskType.ion_channel_fitting]

    assert (
        definition.resources.image_type
        == MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus
    )


def test_it_installs_the_builder_the_task_imports_behind_a_try_except():
    """obi-one does not depend on ion_channel_builder, so without this the task would run
    against its no-op stubs and register an empty model rather than failing.
    """
    definition = TASK_DEFINITIONS[TaskType.ion_channel_fitting]

    assert definition.code.dependencies.endswith("ion_channel_fitting.txt")

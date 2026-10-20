from pathlib import Path

from app import mappings
from app.mappings import TASK_DEFINITIONS
from app.types import TaskType


def test_it_installs_the_builder_the_task_imports_behind_a_try_except():
    dependencies = TASK_DEFINITIONS[TaskType.ion_channel_fitting].code.dependencies
    in_file = Path(mappings.__file__).resolve().parents[1] / Path(dependencies).with_suffix(".in")

    assert "ion-channel-builder" in in_file.read_text()

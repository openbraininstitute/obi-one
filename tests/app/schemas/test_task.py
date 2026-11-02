from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.task import TaskLaunchSubmit
from obi_one.types import TaskType


@pytest.mark.parametrize(
    "task_type",
    [TaskType.circuit_extraction, TaskType.circuit_single_build],
)
def test_task_launch_submit_accepts_launchable_task_type(task_type):
    """Launchable task types should be accepted."""
    model = TaskLaunchSubmit(task_type=task_type, config_id=uuid4())
    assert model.task_type == task_type


def test_task_launch_submit_rejects_non_launchable_task_type():
    """Non-launchable task types should raise a validation error."""
    with pytest.raises(ValidationError, match="not launchable"):
        TaskLaunchSubmit(task_type=TaskType.basic_connectivity_plots, config_id=uuid4())

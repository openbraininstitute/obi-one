"""Import boundaries for task packages with split config/task modules."""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys

import pytest


@pytest.mark.parametrize("package", ["", ".neuron", ".nest"])
def test_simulation_execution_config_import_does_not_load_task_modules(package):
    script = f"""
import sys
import obi_one.scientific.tasks.simulation_execution{package}.config
loaded = [m for m in sys.modules if m.startswith("obi_one.scientific.tasks.simulation_execution")
          and m.endswith(".task")]
assert not loaded, loaded
"""
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", script],
        check=True,
    )


def test_task_spec_neurodamus_execution_single_config_ref_does_not_load_task_module():
    script = """
import sys
from obi_one.scientific.mappings_and_registry.config_task_map import TASK_SPECS
from obi_one.types import TaskType
from obi_one.utils.lazy_import import import_class

spec = TASK_SPECS[TaskType.circuit_simulation_neurodamus_machine]
import_class(spec.single_config_ref)
assert "obi_one.scientific.tasks.simulation_execution.neuron.task" not in sys.modules
"""
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", script],
        check=True,
    )

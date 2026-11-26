"""Task modules must import without the connectivity extra.

Launch workers that do not install ``obi-one[connectivity]`` still import the task class
via ``config_task_map`` / ``run_task_type``. Missing ``conntility`` /
``connectome_manipulator`` must not break that import; execution can raise a clear error.
"""

import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from pathlib import Path

import pytest

from obi_one.scientific.mappings_and_registry.config_task_map import TASK_SPECS
from obi_one.types import TaskType

_REPO_ROOT = Path(__file__).resolve().parents[4]

# Launch deps that pin ``obi-one[connectivity…]`` (relative to repo root).
_CONNECTIVITY_LAUNCH_DEPS = (
    "launch_scripts/launch_circuit_asset_generation/dependencies/default.txt",
    "launch_scripts/launch_task_for_single_config_asset/dependencies/circuit_extraction.txt",
    "launch_scripts/launch_task_for_single_config_asset/dependencies/circuit_simplification.txt",
    "launch_scripts/launch_task_for_single_config_asset/dependencies/em_synapse_mapping.txt",
    "launch_scripts/launch_task_for_single_config_asset/dependencies/synapse_parameterization.txt",
)

# Task types launched with a deps file that includes the connectivity extra.
_TASKS_WITH_CONNECTIVITY_LAUNCH_DEPS = frozenset(
    {
        TaskType.circuit_extraction,
        TaskType.circuit_simplification,
        TaskType.circuit_synaptic_physiology_assignment,
        TaskType.em_synapse_mapping,
    }
)


def test_connectivity_launch_deps_declare_the_extra():
    """Sanity-check the connectivity launch set still pins the extra."""
    for rel in _CONNECTIVITY_LAUNCH_DEPS:
        path = _REPO_ROOT / rel
        obi_lines = [line for line in path.read_text().splitlines() if line.startswith("obi-one")]
        assert obi_lines, path
        assert any("connectivity" in line for line in obi_lines), (path, obi_lines)


@pytest.mark.parametrize(
    "task_type",
    sorted(
        (tt for tt, spec in TASK_SPECS.items() if spec.task_ref is not None),
        key=lambda tt: tt.name,
    ),
)
def test_task_module_imports_without_connectivity_packages(task_type: TaskType):
    """Import task (+ config) classes with conntility/manipulator blocked.

    Tasks launched with ``[connectivity]`` still must import cleanly when those packages
    are absent so config-only / ClassRef loads do not require the extra; runtime execute
    paths raise ``CONNECTIVITY_INSTALL_HINT`` instead.
    """
    spec = TASK_SPECS[task_type]
    refs = [spec.task_ref, spec.single_config_ref, spec.scan_config_ref]
    ref_repr = ", ".join(repr(ref) for ref in refs if ref is not None)
    script = f"""
import sys

BLOCK = {{"conntility", "connectome_manipulator"}}

class BlockFinder:
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".", 1)[0] in BLOCK:
            raise ImportError(f"blocked optional package: {{fullname}}")
        return None

for name in list(sys.modules):
    if name.split(".", 1)[0] in BLOCK:
        del sys.modules[name]

sys.meta_path.insert(0, BlockFinder())

from obi_one.utils.lazy_import import import_class

for ref in ({ref_repr},):
    import_class(ref)

loaded = [m for m in sys.modules if m.split(".", 1)[0] in BLOCK]
assert not loaded, loaded
"""
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", script],
        check=True,
    )


def test_tasks_without_connectivity_launch_deps_are_documented():
    """Non-connectivity launch tasks are covered by the import parametrization above."""
    # Spot-check a few high-traffic workers that must not require the extra at import.
    for task_type in (
        TaskType.circuit_single_build,
        TaskType.circuit_simulation_neurodamus_machine,
        TaskType.morphology_skeletonization,
        TaskType.efeature_extraction,
        TaskType.memodel_build,
    ):
        assert task_type not in _TASKS_WITH_CONNECTIVITY_LAUNCH_DEPS
        assert TASK_SPECS[task_type].task_ref is not None

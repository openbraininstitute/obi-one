"""Tests for per-task obi-one version pinning in app.mappings."""

import pytest

from app import mappings
from app.schemas.task import PythonRepositoryCode, TaskDefinition
from app.types import TaskType


def _first_repository_task() -> TaskType:
    for task_type, task_def in mappings.TASK_DEFINITIONS.items():
        if isinstance(task_def, TaskDefinition) and isinstance(task_def.code, PythonRepositoryCode):
            return task_type
    pytest.skip("No PythonRepositoryCode task available")
    raise AssertionError  # unreachable


def test_apply_obi_one_version_pins_sets_ref_and_constraint(monkeypatch):
    task_type = _first_repository_task()
    original_def = mappings.TASK_DEFINITIONS[task_type]

    monkeypatch.setattr(mappings, "_PINNED_OBI_ONE_VERSIONS", {task_type: "2026.5.1"})
    try:
        mappings._apply_obi_one_version_pins()

        pinned = mappings.TASK_DEFINITIONS[task_type]
        assert pinned.code.ref == "tag:2026.5.1"
        # Constraint pinned to the same version; extras still read from the file.
        assert pinned.code.dependency_constraints
        assert all(c.endswith("==2026.5.1") for c in pinned.code.dependency_constraints)
    finally:
        # Restore the module-level dict to avoid leaking state into other tests.
        mappings.TASK_DEFINITIONS[task_type] = original_def


def test_apply_obi_one_version_pins_unknown_task(monkeypatch):
    # circuit_simulation is a TaskGroupLegacyDefinition (no PythonRepositoryCode).
    monkeypatch.setattr(
        mappings, "_PINNED_OBI_ONE_VERSIONS", {TaskType.circuit_simulation: "2026.5.1"}
    )
    with pytest.raises(RuntimeError, match="Cannot pin obi-one version"):
        mappings._apply_obi_one_version_pins()

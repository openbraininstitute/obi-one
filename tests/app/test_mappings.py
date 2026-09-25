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


def test_apply_obi_one_version_pins_sets_ref_and_constraint():
    task_type = _first_repository_task()
    original_ref = mappings.TASK_DEFINITIONS[task_type].code.ref

    pinned_defs = mappings.apply_obi_one_version_pins(
        mappings.TASK_DEFINITIONS, {task_type: "2026.5.1"}
    )

    pinned = pinned_defs[task_type]
    assert pinned.code.ref == "tag:2026.5.1"
    # Constraint pinned to the same version; extras still read from the file.
    assert pinned.code.dependency_constraints
    assert all(c.endswith("==2026.5.1") for c in pinned.code.dependency_constraints)
    # The input mapping is not mutated (pure function).
    assert mappings.TASK_DEFINITIONS[task_type].code.ref == original_ref


def test_apply_obi_one_version_pins_unknown_task():
    # circuit_simulation is a TaskGroupLegacyDefinition (no PythonRepositoryCode).
    with pytest.raises(RuntimeError, match="Cannot pin obi-one version"):
        mappings.apply_obi_one_version_pins(
            mappings.TASK_DEFINITIONS, {TaskType.circuit_simulation: "2026.5.1"}
        )

"""Tests for per-task obi-one version pinning in app.mappings."""

import pytest

from app import mappings
from app.config import settings
from app.schemas.task import PythonRepositoryCode, TaskDefinition
from app.types import TaskType
from obi_one.utils.versions import build_launch_code_deps


def test_obi_one_dependency_constraints_match_their_file():
    """Every obi-one repository task's constraint is derived from its own deps file.

    Each task's ``dependency_constraints`` must equal what ``build_launch_code_deps``
    derives from its ``dependencies`` file, so a task cannot point at one file while
    constraining a different one (drift). An explicit empty constraint is allowed
    (the derivation is empty for dev/unreleased versions too); the mechanism itself
    is tested in ``tests/obi_one/utils/test_versions.py``.
    """
    checked = 0
    for task_type, task_def in mappings.TASK_DEFINITIONS.items():
        code = getattr(task_def, "code", None)
        if not isinstance(code, PythonRepositoryCode):
            continue
        try:
            expected = build_launch_code_deps(code.dependencies, settings.APP_VERSION)
        except (FileNotFoundError, ValueError):
            continue  # legacy tasks whose requirements don't reference obi-one
        assert code.dependency_constraints == expected["dependency_constraints"], (
            f"{task_type!r}: dependency_constraints out of sync with its dependencies file"
        )
        checked += 1
    assert checked > 0  # sanity: the guard actually exercised some tasks


def _first_repository_task() -> TaskType:
    for task_type, task_def in mappings.TASK_DEFINITIONS.items():
        if isinstance(task_def, TaskDefinition) and isinstance(task_def.code, PythonRepositoryCode):
            return task_type
    pytest.skip("No PythonRepositoryCode task available")
    raise AssertionError  # unreachable


def test_apply_obi_one_version_pins_sets_ref_and_constraint():
    task_type = _first_repository_task()
    original_ref = mappings.TASK_DEFINITIONS[task_type].code.ref

    pinned_defs = mappings._apply_obi_one_version_pins(
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
        mappings._apply_obi_one_version_pins(
            mappings.TASK_DEFINITIONS, {TaskType.circuit_simulation: "2026.5.1"}
        )

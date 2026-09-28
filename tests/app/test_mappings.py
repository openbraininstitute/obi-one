"""Tests for task-definition building and obi-one version pinning in app.mappings."""

import pytest

from app import mappings
from app.schemas.task import PythonRepositoryCode, TaskDefinition
from app.types import TaskType


def test_obi_one_code_uses_app_version(monkeypatch):
    monkeypatch.setattr(mappings.settings, "APP_VERSION", "2026.9.1")
    code = mappings._obi_one_code("circuit_extraction.txt")
    assert code.ref == "tag:2026.9.1"
    assert code.dependency_constraints == ["obi-one[connectivity]==2026.9.1"]


def test_obi_one_code_explicit_version_without_extras(monkeypatch):
    monkeypatch.setattr(mappings.settings, "APP_VERSION", "2026.9.1")
    code = mappings._obi_one_code("default.txt", version="2026.5.1")
    assert code.ref == "tag:2026.5.1"
    assert code.dependency_constraints == ["obi-one==2026.5.1"]


def test_task_definitions_keyed_by_task_type():
    for task_type, task_def in mappings.TASK_DEFINITIONS.items():
        assert task_def.task_type == task_type


def test_build_task_definitions_rejects_duplicates():
    task_def = mappings.TASK_DEFINITIONS[TaskType.circuit_extraction]
    with pytest.raises(ValueError, match="Duplicate task definition"):
        mappings._build_task_definitions((task_def, task_def), {})


def test_build_task_definitions_applies_pin(monkeypatch):
    # Dev service version (no constraint), pinned task gets a full release pin.
    monkeypatch.setattr(mappings.settings, "APP_VERSION", None)
    task_def = mappings.TASK_DEFINITIONS[TaskType.morphology_skeletonization]
    assert isinstance(task_def, TaskDefinition)
    original = task_def.code
    assert isinstance(original, PythonRepositoryCode)

    result = mappings._build_task_definitions(
        (task_def,), {TaskType.morphology_skeletonization: "2026.5.1"}
    )

    pinned_def = result[TaskType.morphology_skeletonization]
    assert isinstance(pinned_def, TaskDefinition)
    pinned = pinned_def.code
    assert isinstance(pinned, PythonRepositoryCode)
    assert pinned.ref == "tag:2026.5.1"
    assert pinned.dependency_constraints == ["obi-one==2026.5.1"]
    assert pinned.dependencies == original.dependencies
    assert pinned.capabilities == original.capabilities  # preserved
    assert original.ref != "tag:2026.5.1"  # input not mutated


@pytest.mark.parametrize(
    "task_type",
    [
        TaskType.circuit_simulation,  # task group, no code
        TaskType.circuit_simulation_brian2_machine,  # bespoke obi-one entrypoint
        TaskType.circuit_simulation_inait_machine,  # different repo
    ],
)
def test_build_task_definitions_rejects_unpinnable(task_type):
    task_def = mappings.TASK_DEFINITIONS[task_type]
    with pytest.raises(ValueError, match="Cannot pin obi-one version"):
        mappings._build_task_definitions((task_def,), {task_type: "2026.5.1"})


def test_build_task_definitions_rejects_unknown_pin():
    with pytest.raises(ValueError, match="Cannot pin obi-one version"):
        mappings._build_task_definitions((), {TaskType.circuit_extraction: "2026.5.1"})

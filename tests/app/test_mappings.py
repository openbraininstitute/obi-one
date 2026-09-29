"""Tests for task-definition building and obi-one version pinning in app.mappings."""

import pytest

from app import mappings
from app.schemas.task import PythonRepositoryCode
from app.types import TaskType


def test_obi_one_code_uses_app_version(monkeypatch):
    monkeypatch.setattr(mappings.settings, "APP_VERSION", "2026.9.1")
    code = mappings._obi_one_code("circuit_extraction.txt")
    assert code.ref == "tag:launch-2026.9.1"
    assert code.dependencies == str(mappings.OBI_ONE_DEPS_DIR / "circuit_extraction.txt")
    assert "dependency_constraints" not in code.model_dump()


def test_obi_one_code_dev_version_uses_last_release(monkeypatch):
    monkeypatch.setattr(mappings.settings, "APP_VERSION", "2026.9.1-3-gabc1234-dirty")
    code = mappings._obi_one_code("default.txt")
    assert code.ref == "tag:launch-2026.9.1"


def test_task_definitions_keyed_by_task_type():
    for task_type, task_def in mappings.TASK_DEFINITIONS.items():
        assert task_def.task_type == task_type


def test_build_task_definitions_rejects_duplicates():
    task_def = mappings.TASK_DEFINITIONS[TaskType.circuit_extraction]
    with pytest.raises(ValueError, match="Duplicate task definition"):
        mappings._build_task_definitions((task_def, task_def), {})


@pytest.mark.parametrize(
    "task_type",
    [
        TaskType.morphology_skeletonization,  # _obi_one_code with capabilities
        TaskType.circuit_simulation_brian2_machine,  # obi-one repo, own script and deps
    ],
)
def test_build_task_definitions_applies_pin(task_type):
    task_def = mappings.TASK_DEFINITIONS[task_type]
    original = task_def.code
    assert isinstance(original, PythonRepositoryCode)

    result = mappings._build_task_definitions((task_def,), {task_type: "2026.5.1"})

    pinned = result[task_type].code
    assert isinstance(pinned, PythonRepositoryCode)
    assert pinned.ref == "tag:launch-2026.5.1"
    # Everything but the ref is preserved, and the input is not mutated.
    assert pinned.model_dump(exclude={"ref"}) == original.model_dump(exclude={"ref"})
    assert original.ref != "tag:launch-2026.5.1"


@pytest.mark.parametrize(
    "task_type",
    [
        TaskType.circuit_simulation,  # task group, no code
        TaskType.circuit_simulation_inait_machine,  # different repo
        TaskType.circuit_simulation_neurodamus_cluster,  # launch-system builtin script
        TaskType.emodel_optimization,  # launch-system builtin script
    ],
)
def test_build_task_definitions_rejects_unpinnable(task_type):
    task_def = mappings.TASK_DEFINITIONS[task_type]
    with pytest.raises(ValueError, match="Cannot pin obi-one version"):
        mappings._build_task_definitions((task_def,), {task_type: "2026.5.1"})


def test_build_task_definitions_rejects_unknown_pin():
    with pytest.raises(ValueError, match="Cannot pin obi-one version"):
        mappings._build_task_definitions((), {TaskType.circuit_extraction: "2026.5.1"})

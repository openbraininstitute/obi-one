"""Tests for task-definition building in app.mappings."""

import pytest

from app import mappings
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
        mappings._build_task_definitions((task_def, task_def))

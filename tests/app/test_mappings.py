"""Tests for task-definition building in app.mappings."""

from pathlib import Path

import launch_deps_compile
import pytest

from app import mappings
from app.schemas.task import PythonRepositoryCode
from app.types import TaskType

REPO_ROOT = Path(mappings.__file__).resolve().parents[1]


def _obi_one_codes() -> list[PythonRepositoryCode]:
    """Code of the task definitions pointing at the obi-one repo, whose files are checked here."""
    return [
        task_def.code
        for task_def in mappings.TASK_DEFINITIONS.values()
        if isinstance(getattr(task_def, "code", None), PythonRepositoryCode)
        and task_def.code.location == mappings.settings.OBI_ONE_REPO
    ]


def test_obi_one_code_uses_app_version(monkeypatch):
    monkeypatch.setattr(mappings.settings, "APP_VERSION", "2026.9.1")
    code = mappings._obi_one_code("circuit_extraction.txt")
    assert code.ref == "tag:2026.9.1"
    assert code.dependencies == str(mappings.OBI_ONE_DEPS_DIR / "circuit_extraction.txt")
    assert "dependency_constraints" not in code.model_dump()


def test_obi_one_code_dev_version_uses_last_release(monkeypatch):
    monkeypatch.setattr(mappings.settings, "APP_VERSION", "2026.9.1-3-gabc1234-dirty")
    code = mappings._obi_one_code("default.txt")
    assert code.ref == "tag:2026.9.1"


def test_task_definitions_keyed_by_task_type():
    for task_type, task_def in mappings.TASK_DEFINITIONS.items():
        assert task_def.task_type == task_type


def test_referenced_dependencies_files_exist():
    """Every requirements file an obi-one task installs must be committed.

    ``dependencies`` is relative to the checkout of ``location``, so only the
    definitions pointing at the obi-one repo can be checked here.
    """
    referenced = {code.dependencies for code in _obi_one_codes()}
    assert referenced  # guard against the filter silently matching nothing
    missing = sorted(path for path in referenced if not (REPO_ROOT / path).is_file())
    assert not missing


def test_private_packages_capability_matches_dependencies():
    """Only tasks whose dependencies need CodeArtifact get its credentials at launch."""
    mismatched = sorted(
        code.dependencies
        for code in _obi_one_codes()
        if code.capabilities.private_packages
        != launch_deps_compile.needs_private_index(
            REPO_ROOT / Path(code.dependencies).with_suffix(".in")
        )
    )
    assert not mismatched


def test_build_task_definitions_rejects_duplicates():
    task_def = mappings.TASK_DEFINITIONS[TaskType.circuit_extraction]
    with pytest.raises(ValueError, match="Duplicate task definition"):
        mappings._build_task_definitions((task_def, task_def))

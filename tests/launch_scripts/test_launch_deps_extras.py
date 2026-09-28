"""Drift check: obi-one extras declared in code match the launch-script deps files.

The extras a launch job installs (``obi-one[extras]``) are declared in code
(``app.mappings.OBI_ONE_DEPS_EXTRAS`` and the circuit launch jobs); the running
service does not read the frozen ``*.txt`` at runtime (they are not in the
installed ``obi_one`` package). This test keeps those declarations consistent with
the source of truth -- the ``obi-one[...]`` line in each requirements file.

It reads the real ``launch_scripts/`` tree, relying on that directory being
available to the test run (pytest ``pythonpath`` + the ``docker-compose.test.yml``
volume), like ``test_compile_launch_deps.py``.
"""

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.mappings import OBI_ONE_DEPS_DIR, OBI_ONE_DEPS_EXTRAS
from obi_one.db_sdk.registration.circuit.launch_jobs import (
    submit_circuit_asset_generation_job,
    submit_circuit_validation_job,
)
from obi_one.utils.versions import OBI_ONE_LINE_REGEX

RELEASE_VERSION = "2026.9.1"  # so obi-one constraints are actually emitted


def _extras_in_deps_file(dependencies: str) -> tuple[str, ...]:
    """Return the obi-one extras declared in the deps file backing ``dependencies``.

    Launch-script ``*.txt`` are generated from a sibling ``*.in`` (the source of
    truth); other requirements files are read directly.
    """
    path = Path(dependencies)
    source = path.with_suffix(".in") if path.suffix == ".txt" else path
    if not source.exists():  # e.g. a library requirements.txt with no .in sibling
        source = path
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = OBI_ONE_LINE_REGEX.match(line)
        if m:
            extras = m.group("extras")
            return tuple(e.strip() for e in extras.split(",") if e.strip()) if extras else ()
    pytest.fail(f"No obi-one requirement found in {source}")
    raise AssertionError  # unreachable


def _extras_from_constraints(constraints: list[str]) -> tuple[str, ...]:
    """Recover obi-one extras from a job's ``dependency_constraints`` list."""
    for constraint in constraints:
        m = OBI_ONE_LINE_REGEX.match(constraint.strip())
        if m:
            extras = m.group("extras")
            return tuple(e.strip() for e in extras.split(",") if e.strip()) if extras else ()
    return ()


def _mock_ls_client() -> MagicMock:
    ls_client = MagicMock()
    ls_client.post.return_value = MagicMock(
        is_success=True, json=MagicMock(return_value={"id": str(uuid4())})
    )
    return ls_client


def _submitted_deps(ls_client: MagicMock) -> tuple[str, tuple[str, ...]]:
    code = ls_client.post.call_args[1]["json"]["code"]
    return code["dependencies"], _extras_from_constraints(code["dependency_constraints"])


def _circuit_job_extras() -> list[tuple[str, str, tuple[str, ...]]]:
    """Yield ``(name, dependencies, declared_extras)`` for the circuit launch jobs.

    The submit helpers are invoked with a mocked client so their real code payload
    is captured, rather than restating the extras here.
    """
    circuit_id, project_id, virtual_lab_id = uuid4(), uuid4(), uuid4()
    validation_client = _mock_ls_client()
    submit_circuit_validation_job(
        ls_client=validation_client,
        circuit_id=circuit_id,
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        api_url="http://localhost",
        compute_cell="cell_a",
        app_version=RELEASE_VERSION,
    )
    asset_client = _mock_ls_client()
    submit_circuit_asset_generation_job(
        ls_client=asset_client,
        circuit_id=circuit_id,
        project_id=project_id,
        virtual_lab_id=virtual_lab_id,
        compute_cell="cell_a",
        app_version=RELEASE_VERSION,
    )
    return [
        ("circuit_validation", *_submitted_deps(validation_client)),
        ("circuit_asset_generation", *_submitted_deps(asset_client)),
    ]


def test_task_definition_extras_match_deps_files():
    for deps_name, declared in OBI_ONE_DEPS_EXTRAS.items():
        dependencies = str(OBI_ONE_DEPS_DIR / deps_name)
        expected = _extras_in_deps_file(dependencies)
        assert set(declared) == set(expected), (
            f"{deps_name}: declared obi-one extras {sorted(declared)} do not match "
            f"{dependencies} ({sorted(expected)})."
        )


def test_circuit_job_extras_match_deps_files():
    jobs = _circuit_job_extras()
    assert jobs  # sanity: the submit helpers were exercised
    for name, dependencies, declared in jobs:
        expected = _extras_in_deps_file(dependencies)
        assert set(declared) == set(expected), (
            f"{name}: declared obi-one extras {sorted(declared)} do not match "
            f"{dependencies} ({sorted(expected)})."
        )

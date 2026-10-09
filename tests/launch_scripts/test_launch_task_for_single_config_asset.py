"""Tests for ``launch_task_for_single_config_asset`` wiring to lazy ``config_task_map``."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from entitysdk.types import ActivityStatus

from obi_one.types import TaskType

pytestmark = pytest.mark.usefixtures("launch_env")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LAUNCH_MAIN = _REPO_ROOT / "launch_scripts/launch_task_for_single_config_asset/main.py"


def _load_launch_main():
    spec = importlib.util.spec_from_file_location("launch_task_main", _LAUNCH_MAIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def launch_main():
    return _load_launch_main()


@pytest.fixture
def argv():
    return [
        "main.py",
        "--task-type",
        "circuit_extraction",
        "--config_entity_id",
        "00000000-0000-0000-0000-000000000001",
        "--execution_activity_id",
        "00000000-0000-0000-0000-000000000002",
        "--entity_cache",
        "True",
        "--scan_output_root",
        "/out",
        "--virtual_lab_id",
        "00000000-0000-0000-0000-000000000003",
        "--project_id",
        "00000000-0000-0000-0000-000000000004",
    ]


@pytest.fixture
def launch_env(tmp_path, monkeypatch):
    store = tmp_path / "local_store"
    store.mkdir()
    monkeypatch.setenv("PERSISTENT_TOKEN_ID", "local-test-token")
    monkeypatch.setenv("DEPLOYMENT", "staging")
    monkeypatch.setenv("LOCAL_STORE_PREFIX", str(store))


def test_main_success_calls_run_task_type_with_task_type_enum(launch_main, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    with (
        patch.object(launch_main, "Client", return_value=MagicMock()),
        patch.object(launch_main, "update_activity_status"),
        patch.object(launch_main, "finalize_activity"),
        patch.object(launch_main, "run_task_type") as run_task_type,
    ):
        assert launch_main.main() == 0

    run_task_type.assert_called_once()
    assert run_task_type.call_args.kwargs["task_type"] is TaskType.circuit_extraction
    assert run_task_type.call_args.kwargs["scan_output_root"] == "/out"


def test_main_failure_finalizes_activity_with_error(launch_main, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    with (
        patch.object(launch_main, "Client", return_value=MagicMock()),
        patch.object(launch_main, "update_activity_status"),
        patch.object(launch_main, "finalize_activity") as finalize_activity,
        patch.object(launch_main, "run_task_type", side_effect=RuntimeError("boom")),
    ):
        assert launch_main.main() == 1

    finalize_activity.assert_called()
    assert finalize_activity.call_args.kwargs["status"] is ActivityStatus.error

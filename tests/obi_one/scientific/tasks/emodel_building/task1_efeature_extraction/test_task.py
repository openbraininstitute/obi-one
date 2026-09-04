"""Tests for EModelEFeatureExtractionTask — focus on activity update.

These tests inject fake ``bluepyemodel`` modules into ``sys.modules`` so they
run regardless of whether the optional ``emodel`` extra is installed.
"""

import sys
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest

from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task import (
    EModelEFeatureExtractionTask,
)

_TASK_MODULE = "obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.task"


def _fake_bluepyemodel_modules() -> dict[str, ModuleType]:
    """Create fake bluepyemodel modules for sys.modules injection."""
    mock_get_access_point = Mock(return_value=Mock())
    mock_extract = Mock()

    ap_mod = ModuleType("bluepyemodel.access_point")
    ap_mod.get_access_point = mock_get_access_point

    extract_mod = ModuleType("bluepyemodel.efeatures_extraction.efeatures_extraction")
    extract_mod.extract_save_features_protocols = mock_extract

    return {
        "bluepyemodel.access_point": ap_mod,
        "bluepyemodel.efeatures_extraction.efeatures_extraction": extract_mod,
    }


@pytest.fixture
def mock_db_client():
    return Mock()


def _make_task(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    config = Mock()
    config.coordinate_output_root = out_dir
    return EModelEFeatureExtractionTask.model_construct(config=config)


@contextmanager
def _noop_chdir(_path):
    yield


class TestEModelEFeatureExtractionTask:
    def test_execute_updates_activity_with_generated_entity(self, tmp_path, mock_db_client):
        """execute() must call _update_execution_activity with the TaskResult ID."""
        task = _make_task(tmp_path)
        task_result_id = uuid4()

        mock_activity = Mock()
        mock_activity.id = uuid4()

        fake_modules = _fake_bluepyemodel_modules()

        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(task, "_download_recordings", return_value=[]),
            patch.object(task, "_build_targets_configuration", return_value=(Mock(), [])),
            patch(f"{_TASK_MODULE}.write_json"),
            patch(f"{_TASK_MODULE}.chdir", _noop_chdir),
            patch.object(
                task,
                "_get_execution_activity",
                return_value=mock_activity,
            ) as mock_get_activity,
            patch.object(
                task, "_register_task_result", return_value=str(task_result_id)
            ) as mock_register,
            patch.object(task, "_update_execution_activity") as mock_update_activity,
        ):
            task.execute(
                db_client=mock_db_client,
                execution_activity_id=str(mock_activity.id),
            )

        mock_get_activity.assert_called_once_with(
            db_client=mock_db_client,
            execution_activity_id=str(mock_activity.id),
        )
        mock_register.assert_called_once()
        mock_update_activity.assert_called_once_with(
            db_client=mock_db_client,
            execution_activity=mock_activity,
            generated=[str(task_result_id)],
        )

    def test_execute_does_not_update_activity_when_registration_fails(
        self, tmp_path, mock_db_client
    ):
        """If _register_task_result raises, _update_execution_activity must not be called."""
        task = _make_task(tmp_path)
        mock_activity = Mock()
        mock_activity.id = uuid4()

        fake_modules = _fake_bluepyemodel_modules()

        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(task, "_download_recordings", return_value=[]),
            patch.object(task, "_build_targets_configuration", return_value=(Mock(), [])),
            patch(f"{_TASK_MODULE}.write_json"),
            patch(f"{_TASK_MODULE}.chdir", _noop_chdir),
            patch.object(task, "_get_execution_activity", return_value=mock_activity),
            patch.object(
                task,
                "_register_task_result",
                side_effect=httpx.HTTPError("network error"),
            ),
            patch.object(task, "_update_execution_activity") as mock_update_activity,
        ):
            task.execute(
                db_client=mock_db_client,
                execution_activity_id=str(mock_activity.id),
            )

        mock_update_activity.assert_not_called()

    def test_execute_skips_activity_update_when_no_db_client(self, tmp_path):
        """Without a db_client, no activity update should happen."""
        task = _make_task(tmp_path)

        fake_modules = _fake_bluepyemodel_modules()

        with (
            patch.dict(sys.modules, fake_modules),
            patch.object(task, "_download_recordings", return_value=[]),
            patch.object(task, "_build_targets_configuration", return_value=(Mock(), [])),
            patch(f"{_TASK_MODULE}.write_json"),
            patch(f"{_TASK_MODULE}.chdir", _noop_chdir),
            patch.object(task, "_update_execution_activity") as mock_update_activity,
        ):
            task.execute(db_client=None)

        mock_update_activity.assert_not_called()

"""Unit tests for circuit registration endpoint helpers."""

import tarfile
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.endpoints.circuit_registration import (
    _extract_archive,
    _trigger_asset_generation_task,
    _trigger_validation_task,
)


class TestExtractArchive:
    def test_valid_tar_gz(self, tmp_path):
        # Create a tar.gz with a circuit_config.json inside
        archive_dir = tmp_path / "src"
        archive_dir.mkdir()
        (archive_dir / "circuit_config.json").write_text('{"networks": {}}')
        (archive_dir / "nodes.h5").write_bytes(b"fake-h5")

        archive_path = tmp_path / "circuit.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(archive_dir / "circuit_config.json", arcname="circuit_config.json")
            tar.add(archive_dir / "nodes.h5", arcname="nodes.h5")

        dest = tmp_path / "output"
        dest.mkdir()
        result = _extract_archive(archive_path, dest)

        assert result.exists()
        assert (result / "circuit_config.json").exists()
        assert (result / "nodes.h5").exists()

    def test_not_a_tarfile_raises(self, tmp_path):
        bad_file = tmp_path / "not_tar.gz"
        bad_file.write_text("this is not a tar file")

        dest = tmp_path / "output"
        dest.mkdir()

        with pytest.raises(HTTPException) as exc_info:
            _extract_archive(bad_file, dest)
        assert exc_info.value.status_code == 422
        assert "tar.gz" in exc_info.value.detail

    def test_empty_archive(self, tmp_path):
        archive_path = tmp_path / "empty.tar.gz"
        with tarfile.open(archive_path, "w:gz"):
            pass  # empty archive

        dest = tmp_path / "output"
        dest.mkdir()
        result = _extract_archive(archive_path, dest)
        assert result.exists()
        assert list(result.iterdir()) == []


class TestTriggerValidationTask:
    @patch("app.endpoints.circuit_registration.settings")
    def test_success(self, mock_settings):
        mock_settings.API_URL = "http://localhost:8100"
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = True
        ls_client.post.return_value = response

        circuit_id = uuid4()
        project_id = uuid4()
        virtual_lab_id = uuid4()

        _trigger_validation_task(
            ls_client=ls_client,
            circuit_id=circuit_id,
            project_id=project_id,
            virtual_lab_id=virtual_lab_id,
        )

        ls_client.post.assert_called_once()
        call_kwargs = ls_client.post.call_args[1]
        assert call_kwargs["url"] == "/job"
        job_data = call_kwargs["json"]
        assert f"--circuit_id {circuit_id}" in job_data["inputs"]
        assert str(project_id) == job_data["project_id"]

    @patch("app.endpoints.circuit_registration.settings")
    def test_failure_logs_warning(self, mock_settings):
        mock_settings.API_URL = "http://localhost:8100"
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = False
        response.text = "server error"
        ls_client.post.return_value = response

        _trigger_validation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
        )
        ls_client.post.assert_called_once()


class TestTriggerAssetGenerationTask:
    @patch("app.endpoints.circuit_registration.settings")
    def test_success(self, mock_settings):
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = "1.2.3-dev"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = True
        ls_client.post.return_value = response

        circuit_id = uuid4()
        project_id = uuid4()
        virtual_lab_id = uuid4()

        _trigger_asset_generation_task(
            ls_client=ls_client,
            circuit_id=circuit_id,
            project_id=project_id,
            virtual_lab_id=virtual_lab_id,
        )

        ls_client.post.assert_called_once()
        call_kwargs = ls_client.post.call_args[1]
        job_data = call_kwargs["json"]
        assert "tag:1.2.3" in job_data["code"]["ref"]
        assert f"--circuit_id {circuit_id}" in job_data["inputs"]

    @patch("app.endpoints.circuit_registration.settings")
    def test_none_app_version(self, mock_settings):
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = None

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = True
        ls_client.post.return_value = response

        _trigger_asset_generation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
        )

        call_kwargs = ls_client.post.call_args[1]
        job_data = call_kwargs["json"]
        assert "tag:0.0.0" in job_data["code"]["ref"]

    @patch("app.endpoints.circuit_registration.settings")
    def test_failure_logs_warning(self, mock_settings):
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = "2.0.0"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = False
        response.text = "internal error"
        ls_client.post.return_value = response

        _trigger_asset_generation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
        )
        ls_client.post.assert_called_once()


# ---------------------------------------------------------------------------
# generate_assets_endpoint unit test
# ---------------------------------------------------------------------------


class TestGenerateAssetsEndpoint:
    """Test generate_assets_endpoint via TestClient."""

    def test_rejects_non_active_circuit(self, client):
        """Circuit with lifecycle_status != active should be rejected."""
        from unittest.mock import patch  # noqa: PLC0415

        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "draft"
        mock_circuit.assets = []

        with patch("app.endpoints.circuit_registration.get_client") as mock_get_client:
            mock_db = MagicMock()
            mock_db.get_entity.return_value = mock_circuit
            mock_get_client.return_value = mock_db

            from app.application import app  # noqa: PLC0415
            from app.dependencies.entitysdk import get_client  # noqa: PLC0415

            app.dependency_overrides[get_client] = lambda: mock_db

            try:
                resp = client.post(f"/declared/circuit/{circuit_id}/generate-assets")
                assert resp.status_code == 409
                assert "lifecycle_status" in resp.json()["detail"]
            finally:
                app.dependency_overrides.pop(get_client, None)

    def test_returns_already_exists(self, client):
        """If assets already exist and not force, returns message."""

        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "active"

        # Fake assets with the required labels
        asset1 = MagicMock()
        asset1.label = "compressed_sonata_circuit"
        asset2 = MagicMock()
        asset2.label = "circuit_connectivity_matrices"
        mock_circuit.assets = [asset1, asset2]

        from app.application import app  # noqa: PLC0415
        from app.dependencies.entitysdk import get_client  # noqa: PLC0415

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        app.dependency_overrides[get_client] = lambda: mock_db

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/generate-assets")
            assert resp.status_code == 200
            assert "already exist" in resp.json()["message"]
        finally:
            app.dependency_overrides.pop(get_client, None)

"""Unit tests for circuit registration endpoint helpers."""

import tarfile
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.endpoints.circuit_helpers import (
    trigger_asset_generation_task,
    trigger_validation_task,
)
from app.endpoints.circuit_registration import register_circuit_endpoint
from obi_one.utils.io import extract_tar_gz


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

        dest = tmp_path / "output" / "circuit"
        result = extract_tar_gz(archive_path, output_dir=dest, clean=True)

        assert result.exists()
        assert (result / "circuit_config.json").exists()
        assert (result / "nodes.h5").exists()

    def test_not_a_tarfile_raises(self, tmp_path):
        bad_file = tmp_path / "not_tar.gz"
        bad_file.write_text("this is not a tar file")

        dest = tmp_path / "output" / "circuit"
        with pytest.raises((OSError, tarfile.TarError, tarfile.ReadError)):
            extract_tar_gz(bad_file, output_dir=dest, clean=True)


class TestTriggerValidationTask:
    @patch("app.endpoints.circuit_helpers.settings")
    def test_success(self, mock_settings):
        mock_settings.API_URL = "http://localhost:8100"
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = "1.2.3-dev"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = True
        ls_client.post.return_value = response

        circuit_id = uuid4()
        project_id = uuid4()
        virtual_lab_id = uuid4()

        trigger_validation_task(
            ls_client=ls_client,
            circuit_id=circuit_id,
            project_id=project_id,
            virtual_lab_id=virtual_lab_id,
        )

        ls_client.post.assert_called_once()
        call_kwargs = ls_client.post.call_args[1]
        assert call_kwargs["url"] == "/job"
        job_data = call_kwargs["json"]
        assert job_data["code"]["ref"] == "tag:1.2.3"
        assert f"--circuit_id {circuit_id}" in job_data["inputs"]
        assert "--force false" in job_data["inputs"]
        assert str(project_id) == job_data["project_id"]

    @patch("app.endpoints.circuit_helpers.settings")
    def test_forwards_force_true(self, mock_settings):
        mock_settings.API_URL = "http://localhost:8100"
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = "1.2.3"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = True
        ls_client.post.return_value = response

        trigger_validation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
            force=True,
        )

        job_data = ls_client.post.call_args[1]["json"]
        assert "--force true" in job_data["inputs"]

    @patch("app.endpoints.circuit_helpers.settings")
    def test_failure_logs_warning(self, mock_settings):
        mock_settings.API_URL = "http://localhost:8100"
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = None

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = False
        response.text = "server error"
        ls_client.post.return_value = response

        trigger_validation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
        )
        ls_client.post.assert_called_once()
        assert ls_client.post.call_args[1]["json"]["code"]["ref"] == "tag:0.0.0"
        assert "--force false" in ls_client.post.call_args[1]["json"]["inputs"]


# ---------------------------------------------------------------------------
# validate_circuit_endpoint unit test
# ---------------------------------------------------------------------------


class TestValidateCircuitEndpoint:
    """Test validate_circuit_endpoint via TestClient."""

    def test_rejects_non_draft_without_force(self, client):
        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "active"

        from app.application import app  # noqa: PLC0415
        from app.dependencies.entitysdk import get_client  # noqa: PLC0415

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        app.dependency_overrides[get_client] = lambda: mock_db

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/validate")
            assert resp.status_code == 409
            assert "force=true" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_client, None)

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    def test_force_triggers_validation(self, mock_trigger, client):
        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "active"

        from app.application import app  # noqa: PLC0415
        from app.dependencies.entitysdk import get_client  # noqa: PLC0415

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        mock_db.project_context.project_id = uuid4()
        mock_db.project_context.virtual_lab_id = uuid4()
        app.dependency_overrides[get_client] = lambda: mock_db

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/validate?force=true")
            assert resp.status_code == 200
            assert resp.json()["status"] == "validation_triggered"
            mock_trigger.assert_called_once()
            assert mock_trigger.call_args.kwargs["force"] is True
        finally:
            app.dependency_overrides.pop(get_client, None)

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    def test_draft_triggers_without_force(self, mock_trigger, client):
        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "draft"

        from app.application import app  # noqa: PLC0415
        from app.dependencies.entitysdk import get_client  # noqa: PLC0415

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        mock_db.project_context.project_id = uuid4()
        mock_db.project_context.virtual_lab_id = uuid4()
        app.dependency_overrides[get_client] = lambda: mock_db

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/validate")
            assert resp.status_code == 200
            mock_trigger.assert_called_once()
            assert mock_trigger.call_args.kwargs["force"] is False
        finally:
            app.dependency_overrides.pop(get_client, None)


class TestTriggerAssetGenerationTask:
    @patch("app.endpoints.circuit_helpers.settings")
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

        trigger_asset_generation_task(
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
        assert "--force false" in job_data["inputs"]

    @patch("app.endpoints.circuit_helpers.settings")
    def test_forwards_force_true(self, mock_settings):
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = "1.2.3"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = True
        ls_client.post.return_value = response

        trigger_asset_generation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
            force=True,
        )

        job_data = ls_client.post.call_args[1]["json"]
        assert "--force true" in job_data["inputs"]

    @patch("app.endpoints.circuit_helpers.settings")
    def test_none_app_version(self, mock_settings):
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = None

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = True
        ls_client.post.return_value = response

        trigger_asset_generation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
        )

        call_kwargs = ls_client.post.call_args[1]
        job_data = call_kwargs["json"]
        assert "tag:0.0.0" in job_data["code"]["ref"]

    @patch("app.endpoints.circuit_helpers.settings")
    def test_failure_logs_warning(self, mock_settings):
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.APP_VERSION = "2.0.0"

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = False
        response.text = "internal error"
        ls_client.post.return_value = response

        trigger_asset_generation_task(
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


class TestRegisterCircuitEndpoint:
    """Test register_circuit_endpoint delegates to library register_circuit."""

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    @patch("app.endpoints.circuit_registration.register_circuit")
    def test_registers_circuit_with_draft_lifecycle_status(
        self,
        mock_register_circuit,
        mock_trigger_validation,
    ):
        """Endpoint must call register_circuit with draft + skip_validation."""
        mock_registered = MagicMock()
        mock_registered.id = uuid4()
        mock_registered.name = "test-circuit"
        mock_registered.number_neurons = 1000
        mock_registered.number_synapses = 5000
        mock_registered.number_connections = 2000
        mock_registered.scale = "small"
        mock_register_circuit.return_value = mock_registered

        mock_db_client = MagicMock()
        mock_brain_region = MagicMock()
        mock_subject = MagicMock()
        mock_db_client.get_entity.side_effect = [mock_brain_region, mock_subject]
        mock_db_client.project_context.project_id = uuid4()
        mock_db_client.project_context.virtual_lab_id = uuid4()

        mock_ls_client = MagicMock()
        mock_upload = MagicMock()
        mock_upload.filename = "circuit.tar.gz"
        mock_upload.file.read.return_value = b"fake-archive"

        result = register_circuit_endpoint(
            ls_client=mock_ls_client,
            db_client=mock_db_client,
            name="test-circuit",
            description="A test circuit",
            brain_region_id=uuid4(),
            subject_id=uuid4(),
            build_category="synaptic",
            target_simulator="SONATA",
            circuit_archive=mock_upload,
            parent_circuit_id=None,
            derivation_type=None,
            atlas_id=None,
            license_id=None,
            contact_email=None,
            authorized_public=False,
        )

        mock_register_circuit.assert_called_once()
        call_kwargs = mock_register_circuit.call_args.kwargs
        assert call_kwargs["lifecycle_status"] == "draft"
        assert call_kwargs["skip_validation"] is True
        assert call_kwargs["include_visualization"] is True
        assert call_kwargs["name"] == "test-circuit"

        assert result["status"] == "draft"
        assert result["number_neurons"] == 1000
        mock_trigger_validation.assert_called_once()

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    @patch("app.endpoints.circuit_registration.register_circuit")
    def test_invalid_archive_returns_422(self, mock_register_circuit, mock_trigger_validation):
        mock_register_circuit.side_effect = tarfile.TarError("bad archive")

        mock_db_client = MagicMock()
        mock_db_client.get_entity.side_effect = [MagicMock(), MagicMock()]
        mock_db_client.project_context.project_id = uuid4()
        mock_db_client.project_context.virtual_lab_id = uuid4()

        mock_upload = MagicMock()
        mock_upload.filename = "circuit.tar.gz"
        mock_upload.file.read.return_value = b"not-a-tar"

        with pytest.raises(HTTPException) as exc_info:
            register_circuit_endpoint(
                ls_client=MagicMock(),
                db_client=mock_db_client,
                name="test-circuit",
                description="A test circuit",
                brain_region_id=uuid4(),
                subject_id=uuid4(),
                build_category="synaptic",
                target_simulator="NEURON",
                circuit_archive=mock_upload,
            )

        assert exc_info.value.status_code == 422
        mock_trigger_validation.assert_not_called()

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
            compute_cell="cell_a",
        )

        ls_client.post.assert_called_once()
        call_kwargs = ls_client.post.call_args[1]
        assert call_kwargs["url"] == "/job"
        job_data = call_kwargs["json"]
        assert job_data["code"]["ref"] == "tag:1.2.3"
        assert job_data["resources"]["image_type"] == "python_3_12_openmpi5_neuron9_neurodamus"
        assert job_data["resources"]["compute_cell"] == "cell_a"
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
            compute_cell="cell_b",
            force=True,
        )

        job_data = ls_client.post.call_args[1]["json"]
        assert "--force true" in job_data["inputs"]
        assert job_data["resources"]["compute_cell"] == "cell_b"

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
            compute_cell="cell_a",
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

        from app.application import app  # ruff: ignore[import-outside-top-level]
        from app.dependencies.compute_cell import (  # ruff: ignore[import-outside-top-level]
            get_compute_cell,
        )
        from app.dependencies.entitysdk import get_client  # ruff: ignore[import-outside-top-level]

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        app.dependency_overrides[get_client] = lambda: mock_db
        app.dependency_overrides[get_compute_cell] = lambda: "cell_a"

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/validate")
            assert resp.status_code == 409
            assert "force=true" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_client, None)
            app.dependency_overrides.pop(get_compute_cell, None)

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    def test_force_triggers_validation(self, mock_trigger, client):
        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "active"

        from app.application import app  # ruff: ignore[import-outside-top-level]
        from app.dependencies.compute_cell import (  # ruff: ignore[import-outside-top-level]
            get_compute_cell,
        )
        from app.dependencies.entitysdk import get_client  # ruff: ignore[import-outside-top-level]

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        mock_db.project_context.project_id = uuid4()
        mock_db.project_context.virtual_lab_id = uuid4()
        app.dependency_overrides[get_client] = lambda: mock_db
        app.dependency_overrides[get_compute_cell] = lambda: "cell_a"

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/validate?force=true")
            assert resp.status_code == 200
            assert resp.json()["status"] == "validation_triggered"
            mock_trigger.assert_called_once()
            assert mock_trigger.call_args.kwargs["force"] is True
            assert mock_trigger.call_args.kwargs["compute_cell"] == "cell_a"
        finally:
            app.dependency_overrides.pop(get_client, None)
            app.dependency_overrides.pop(get_compute_cell, None)

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    def test_draft_triggers_without_force(self, mock_trigger, client):
        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "draft"

        from app.application import app  # ruff: ignore[import-outside-top-level]
        from app.dependencies.compute_cell import (  # ruff: ignore[import-outside-top-level]
            get_compute_cell,
        )
        from app.dependencies.entitysdk import get_client  # ruff: ignore[import-outside-top-level]

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        mock_db.project_context.project_id = uuid4()
        mock_db.project_context.virtual_lab_id = uuid4()
        app.dependency_overrides[get_client] = lambda: mock_db
        app.dependency_overrides[get_compute_cell] = lambda: "cell_b"

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/validate")
            assert resp.status_code == 200
            mock_trigger.assert_called_once()
            assert mock_trigger.call_args.kwargs["force"] is False
            assert mock_trigger.call_args.kwargs["compute_cell"] == "cell_b"
        finally:
            app.dependency_overrides.pop(get_client, None)
            app.dependency_overrides.pop(get_compute_cell, None)


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
            compute_cell="cell_a",
        )

        ls_client.post.assert_called_once()
        call_kwargs = ls_client.post.call_args[1]
        job_data = call_kwargs["json"]
        assert "tag:1.2.3" in job_data["code"]["ref"]
        assert job_data["resources"]["compute_cell"] == "cell_a"
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
            compute_cell="cell_b",
            force=True,
        )

        job_data = ls_client.post.call_args[1]["json"]
        assert "--force true" in job_data["inputs"]
        assert job_data["resources"]["compute_cell"] == "cell_b"

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
            compute_cell="cell_a",
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
            compute_cell="cell_a",
        )
        ls_client.post.assert_called_once()


# ---------------------------------------------------------------------------
# generate_assets_endpoint unit test
# ---------------------------------------------------------------------------


class TestGenerateAssetsEndpoint:
    """Test generate_assets_endpoint via TestClient."""

    def test_rejects_non_active_circuit(self, client):
        """Circuit with lifecycle_status != active should be rejected."""
        from unittest.mock import patch  # ruff: ignore[import-outside-top-level]

        circuit_id = uuid4()
        mock_circuit = MagicMock()
        mock_circuit.lifecycle_status = "draft"
        mock_circuit.assets = []

        with patch("app.endpoints.circuit_registration.get_client") as mock_get_client:
            mock_db = MagicMock()
            mock_db.get_entity.return_value = mock_circuit
            mock_get_client.return_value = mock_db

            from app.application import app  # ruff: ignore[import-outside-top-level]
            from app.dependencies.compute_cell import (  # ruff: ignore[import-outside-top-level]
                get_compute_cell,
            )
            from app.dependencies.entitysdk import (  # ruff: ignore[import-outside-top-level]
                get_client,
            )

            app.dependency_overrides[get_client] = lambda: mock_db
            app.dependency_overrides[get_compute_cell] = lambda: "cell_a"

            try:
                resp = client.post(f"/declared/circuit/{circuit_id}/generate-assets")
                assert resp.status_code == 409
                assert "lifecycle_status" in resp.json()["detail"]
            finally:
                app.dependency_overrides.pop(get_client, None)
                app.dependency_overrides.pop(get_compute_cell, None)

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

        from app.application import app  # ruff: ignore[import-outside-top-level]
        from app.dependencies.compute_cell import (  # ruff: ignore[import-outside-top-level]
            get_compute_cell,
        )
        from app.dependencies.entitysdk import get_client  # ruff: ignore[import-outside-top-level]

        mock_db = MagicMock()
        mock_db.get_entity.return_value = mock_circuit
        app.dependency_overrides[get_client] = lambda: mock_db
        app.dependency_overrides[get_compute_cell] = lambda: "cell_a"

        try:
            resp = client.post(f"/declared/circuit/{circuit_id}/generate-assets")
            assert resp.status_code == 200
            assert "already exist" in resp.json()["message"]
        finally:
            app.dependency_overrides.pop(get_client, None)
            app.dependency_overrides.pop(get_compute_cell, None)


class TestRegisterCircuitEndpoint:
    """Test register_circuit_endpoint delegates to library register_circuit."""

    @staticmethod
    def _mock_db_client(*, hierarchy_id=None):
        mock_db_client = MagicMock()
        mock_brain_region = MagicMock()
        mock_brain_region.hierarchy_id = hierarchy_id
        mock_subject = MagicMock()
        mock_db_client.get_entity.side_effect = [mock_brain_region, mock_subject]
        mock_db_client.project_context.project_id = uuid4()
        mock_db_client.project_context.virtual_lab_id = uuid4()
        # Duplicate check: search returns no existing circuit
        mock_db_client.search_entity.return_value.all.return_value = []
        return mock_db_client, mock_brain_region, mock_subject

    @staticmethod
    def _mock_upload(filename: str = "circuit.tar.gz", content: bytes = b"fake-archive"):
        mock_upload = MagicMock()
        mock_upload.filename = filename
        mock_upload.file.read.return_value = content
        return mock_upload

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

        mock_db_client, _, _ = self._mock_db_client()

        result = register_circuit_endpoint(
            ls_client=MagicMock(),
            db_client=mock_db_client,
            compute_cell="cell_a",
            name="test-circuit",
            description="A test circuit",
            brain_region_id=uuid4(),
            subject_id=uuid4(),
            build_category="synaptic",
            target_simulator="SONATA",
            circuit_archive=self._mock_upload(),
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
        assert call_kwargs["dry_run"] is False
        assert call_kwargs["name"] == "test-circuit"
        assert call_kwargs["published_in"] is None
        assert call_kwargs["experiment_date"] is None
        assert call_kwargs["contributions"] is None
        assert call_kwargs["publications"] is None
        assert call_kwargs["overview_image_path"] is None
        assert call_kwargs["sim_designer_image_path"] is None

        assert result["status"] == "draft"
        assert result["number_neurons"] == 1000
        mock_trigger_validation.assert_called_once()
        assert mock_trigger_validation.call_args.kwargs["compute_cell"] == "cell_a"

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    @patch("app.endpoints.circuit_registration.register_circuit")
    def test_dry_run_skips_registration_and_validation(
        self,
        mock_register_circuit,
        mock_trigger_validation,
    ):
        """dry_run computes metadata without registering or launching validation."""
        mock_preview = MagicMock()
        mock_preview.id = None
        mock_preview.number_neurons = 42
        mock_preview.number_synapses = 100
        mock_preview.number_connections = 7
        mock_preview.scale = "pair"
        mock_register_circuit.return_value = mock_preview

        mock_db_client, _, _ = self._mock_db_client()

        result = register_circuit_endpoint(
            ls_client=MagicMock(),
            db_client=mock_db_client,
            compute_cell="cell_a",
            name="dry-run-circuit",
            description="A dry run",
            brain_region_id=uuid4(),
            subject_id=uuid4(),
            build_category="synaptic",
            target_simulator="NEURON",
            circuit_archive=self._mock_upload(),
            dry_run=True,
        )

        call_kwargs = mock_register_circuit.call_args.kwargs
        assert call_kwargs["dry_run"] is True
        assert call_kwargs["skip_additional_assets"] is True
        assert call_kwargs["include_visualization"] is False
        mock_trigger_validation.assert_not_called()
        assert result["status"] == "dry_run"
        assert result["circuit_id"] is None
        assert result["number_neurons"] == 42
        assert result["number_synapses"] == 100
        assert result["number_connections"] == 7
        assert result["scale"] == "pair"

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    @patch("app.endpoints.circuit_registration.register_circuit")
    def test_forwards_metadata_parity_fields(self, mock_register_circuit, mock_trigger_validation):
        """published_in, experiment_date, contributions, publications, images, scale."""
        mock_registered = MagicMock()
        mock_registered.id = uuid4()
        mock_registered.number_neurons = 10
        mock_registered.number_synapses = 20
        mock_registered.number_connections = None
        mock_registered.scale = "microcircuit"
        mock_register_circuit.return_value = mock_registered

        mock_db_client, _, _ = self._mock_db_client()
        resolved_contrib = {"agent": MagicMock()}
        resolved_publ = {"entity": MagicMock()}

        overview = self._mock_upload("overview.png", b"png-bytes")
        sim_img = self._mock_upload("sim.png", b"sim-bytes")

        with (
            patch(
                "app.endpoints.circuit_registration.get_contributions",
                return_value=resolved_contrib,
            ) as mock_get_contrib,
            patch(
                "app.endpoints.circuit_registration.get_publications",
                return_value=resolved_publ,
            ) as mock_get_publ,
        ):
            result = register_circuit_endpoint(
                ls_client=MagicMock(),
                db_client=mock_db_client,
                compute_cell="cell_a",
                name="test-circuit",
                description="A test circuit",
                brain_region_id=uuid4(),
                subject_id=uuid4(),
                build_category="synaptic",
                target_simulator="NEURON",
                circuit_archive=self._mock_upload(),
                scale_override="microcircuit",
                published_in="Nature 2024",
                experiment_date="2024-03-27",
                contributions='{"Jane Doe": {"type": "person", "role": "author"}}',
                publications='{"10.1234/foo": {"type": "entity_source"}}',
                overview_image=overview,
                sim_designer_image=sim_img,
            )

        mock_get_contrib.assert_called_once()
        mock_get_publ.assert_called_once()
        call_kwargs = mock_register_circuit.call_args.kwargs
        assert call_kwargs["published_in"] == "Nature 2024"
        assert call_kwargs["experiment_date"].year == 2024
        assert call_kwargs["experiment_date"].month == 3
        assert call_kwargs["experiment_date"].day == 27
        assert call_kwargs["contributions"] is resolved_contrib
        assert call_kwargs["publications"] is resolved_publ
        assert str(call_kwargs["scale_override"]) == "microcircuit"
        assert call_kwargs["overview_image_path"].name == "overview.png"
        assert call_kwargs["sim_designer_image_path"].name == "sim.png"
        assert result["scale"] == "microcircuit"
        mock_trigger_validation.assert_called_once()

    @patch("app.endpoints.circuit_registration.check_if_circuit_exists")
    def test_duplicate_name_returns_422(self, mock_check_exists):
        mock_check_exists.side_effect = ValueError("Circuit 'test-circuit' already exists!")

        with pytest.raises(HTTPException) as exc_info:
            register_circuit_endpoint(
                ls_client=MagicMock(),
                db_client=MagicMock(),
                compute_cell="cell_a",
                name="test-circuit",
                description="A test circuit",
                brain_region_id=uuid4(),
                subject_id=uuid4(),
                build_category="synaptic",
                target_simulator="NEURON",
                circuit_archive=self._mock_upload(),
            )

        assert exc_info.value.status_code == 422
        assert "already exists" in exc_info.value.detail

    def test_hierarchy_species_mismatch_returns_422(self):
        hierarchy_id = uuid4()
        mock_db_client, mock_brain_region, mock_subject = self._mock_db_client(
            hierarchy_id=hierarchy_id
        )
        mock_hierarchy = MagicMock()
        # get_entity: brain_region, subject, then hierarchy
        mock_db_client.get_entity.side_effect = [
            mock_brain_region,
            mock_subject,
            mock_hierarchy,
        ]

        with (
            patch("app.endpoints.circuit_registration.check_if_circuit_exists"),
            patch(
                "app.endpoints.circuit_registration.check_hierarchy_species",
                side_effect=ValueError("Species mismatch"),
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            register_circuit_endpoint(
                ls_client=MagicMock(),
                db_client=mock_db_client,
                compute_cell="cell_a",
                name="test-circuit",
                description="A test circuit",
                brain_region_id=uuid4(),
                subject_id=uuid4(),
                build_category="synaptic",
                target_simulator="NEURON",
                circuit_archive=self._mock_upload(),
            )

        assert exc_info.value.status_code == 422
        assert "Species mismatch" in exc_info.value.detail

    def test_invalid_contributions_json_returns_422(self):
        with (
            patch("app.endpoints.circuit_registration.check_if_circuit_exists"),
            pytest.raises(HTTPException) as exc_info,
        ):
            register_circuit_endpoint(
                ls_client=MagicMock(),
                db_client=MagicMock(),
                compute_cell="cell_a",
                name="test-circuit",
                description="A test circuit",
                brain_region_id=uuid4(),
                subject_id=uuid4(),
                build_category="synaptic",
                target_simulator="NEURON",
                circuit_archive=self._mock_upload(),
                contributions="not-json",
            )

        assert exc_info.value.status_code == 422
        assert "contributions" in exc_info.value.detail

    @patch("app.endpoints.circuit_registration.trigger_validation_task")
    @patch("app.endpoints.circuit_registration.register_circuit")
    def test_invalid_archive_returns_422(self, mock_register_circuit, mock_trigger_validation):
        mock_register_circuit.side_effect = tarfile.TarError("bad archive")

        mock_db_client, _, _ = self._mock_db_client()

        with pytest.raises(HTTPException) as exc_info:
            register_circuit_endpoint(
                ls_client=MagicMock(),
                db_client=mock_db_client,
                compute_cell="cell_a",
                name="test-circuit",
                description="A test circuit",
                brain_region_id=uuid4(),
                subject_id=uuid4(),
                build_category="synaptic",
                target_simulator="NEURON",
                circuit_archive=self._mock_upload(content=b"not-a-tar"),
            )

        assert exc_info.value.status_code == 422
        mock_trigger_validation.assert_not_called()

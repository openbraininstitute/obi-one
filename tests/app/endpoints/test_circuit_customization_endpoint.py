"""Unit tests for circuit_customization — _trigger_validation_task and _run_validations."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch
from uuid import uuid4

import h5py
import numpy as np
from fastapi import UploadFile

from app.endpoints.circuit_customization import (
    _run_validations,
    _save_uploads,
    _trigger_validation_task,
    _validate_file_groups,
)

# ---------------------------------------------------------------------------
# _save_uploads
# ---------------------------------------------------------------------------


class TestSaveUploads:
    def test_saves_files(self, tmp_path):
        content = b"file content here"
        upload = MagicMock(spec=UploadFile)
        upload.filename = "test.hoc"
        upload.file = BytesIO(content)

        paths = _save_uploads([upload], tmp_path)
        assert len(paths) == 1
        assert paths[0] == tmp_path / "test.hoc"
        assert paths[0].read_bytes() == content

    def test_saves_multiple(self, tmp_path):
        uploads = []
        for name in ["a.mod", "b.mod", "c.mod"]:
            u = MagicMock(spec=UploadFile)
            u.filename = name
            u.file = BytesIO(b"NEURON { SUFFIX X }\n")
            uploads.append(u)

        paths = _save_uploads(uploads, tmp_path)
        assert len(paths) == 3
        assert all(p.exists() for p in paths)


# ---------------------------------------------------------------------------
# _validate_file_groups
# ---------------------------------------------------------------------------


class TestValidateFileGroups:
    def test_all_none(self, tmp_path):
        edge_paths, hoc_paths, mod_paths, node_paths, errors = _validate_file_groups(
            tmp_path, None, None, None, None
        )
        assert edge_paths == []
        assert hoc_paths == []
        assert mod_paths == []
        assert node_paths == []
        assert errors == []

    def test_valid_hoc_file(self, tmp_path):
        upload = MagicMock(spec=UploadFile)
        upload.filename = "cell.hoc"
        upload.file = BytesIO(b"begintemplate X\nendtemplate X\n")

        _, hoc_paths, _, _, errors = _validate_file_groups(tmp_path, None, [upload], None, None)
        assert len(hoc_paths) == 1
        assert errors == []

    def test_invalid_hoc_file(self, tmp_path):
        upload = MagicMock(spec=UploadFile)
        upload.filename = "bad.hoc"
        upload.file = BytesIO(b"no template here\n")

        _, hoc_paths, _, _, errors = _validate_file_groups(tmp_path, None, [upload], None, None)
        assert len(hoc_paths) == 1
        assert len(errors) == 1
        assert "emodels" in errors[0]

    def test_valid_mod_file(self, tmp_path):
        upload = MagicMock(spec=UploadFile)
        upload.filename = "NaTg.mod"
        upload.file = BytesIO(b"NEURON { SUFFIX NaTg }\n")

        _, _, mod_paths, _, errors = _validate_file_groups(tmp_path, None, None, [upload], None)
        assert len(mod_paths) == 1
        assert errors == []

    def test_invalid_mod_file(self, tmp_path):
        upload = MagicMock(spec=UploadFile)
        upload.filename = "bad.mod"
        upload.file = BytesIO(b"no neuron block\n")

        _, _, mod_paths, _, errors = _validate_file_groups(tmp_path, None, None, [upload], None)
        assert len(mod_paths) == 1
        assert len(errors) == 1
        assert "mechanisms" in errors[0]

    def test_valid_edge_file(self, tmp_path):
        # Create an actual HDF5 edge file in memory
        edge_data = BytesIO()
        with h5py.File(edge_data, "w") as f:
            pop = f.create_group("edges/pop_a")
            n = 5
            pop.create_dataset("source_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("target_node_id", data=np.arange(n, dtype=np.int64))
            pop.create_dataset("edge_type_id", data=np.zeros(n, dtype=np.int32))
        edge_data.seek(0)

        upload = MagicMock(spec=UploadFile)
        upload.filename = "edges.h5"
        upload.file = edge_data

        edge_paths, _, _, _, errors = _validate_file_groups(tmp_path, [upload], None, None, None)
        assert len(edge_paths) == 1
        assert errors == []

    def test_invalid_edge_file(self, tmp_path):
        upload = MagicMock(spec=UploadFile)
        upload.filename = "bad_edges.h5"
        upload.file = BytesIO(b"not hdf5 content")

        edge_paths, _, _, _, errors = _validate_file_groups(tmp_path, [upload], None, None, None)
        assert len(edge_paths) == 1
        assert len(errors) == 1
        assert "edges" in errors[0]

    def test_valid_node_file(self, tmp_path):
        node_data = BytesIO()
        with h5py.File(node_data, "w") as f:
            grp = f.create_group("nodes/pop_a")
            grp.create_dataset("node_type_id", data=np.zeros(5, dtype=np.int32))
        node_data.seek(0)

        upload = MagicMock(spec=UploadFile)
        upload.filename = "nodes.h5"
        upload.file = node_data

        _, _, _, node_paths, errors = _validate_file_groups(tmp_path, None, None, None, [upload])
        assert len(node_paths) == 1
        assert errors == []


# ---------------------------------------------------------------------------
# _run_validations (with node_sets)
# ---------------------------------------------------------------------------


class TestRunValidations:
    def test_valid_node_sets(self, tmp_path):
        ns_upload = MagicMock(spec=UploadFile)
        ns_upload.filename = "node_sets.json"
        ns_upload.file = BytesIO(json.dumps({"All": {"population": "default"}}).encode())

        _, _, _, _, ns_path, errors = _run_validations(tmp_path, None, None, None, None, ns_upload)
        assert ns_path is not None
        assert ns_path.exists()
        assert errors == []

    def test_invalid_node_sets(self, tmp_path):
        ns_upload = MagicMock(spec=UploadFile)
        ns_upload.filename = "node_sets.json"
        ns_upload.file = BytesIO(b"not valid json {{")

        _, _, _, _, ns_path, errors = _run_validations(tmp_path, None, None, None, None, ns_upload)
        assert ns_path is not None
        assert len(errors) == 1
        assert "node_sets" in errors[0]

    def test_no_node_sets(self, tmp_path):
        _, _, _, _, ns_path, errors = _run_validations(tmp_path, None, None, None, None, None)
        assert ns_path is None
        assert errors == []


# ---------------------------------------------------------------------------
# _trigger_validation_task
# ---------------------------------------------------------------------------


class TestTriggerValidationTask:
    @patch("app.endpoints.circuit_customization.settings")
    def test_success(self, mock_settings):
        mock_settings.API_URL = "http://localhost:8100"
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.COMMIT_SHA = "abc123"

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

    @patch("app.endpoints.circuit_customization.settings")
    def test_failure_logs_warning(self, mock_settings):
        mock_settings.API_URL = "http://localhost:8100"
        mock_settings.OBI_ONE_REPO = "https://github.com/org/repo.git"
        mock_settings.COMMIT_SHA = ""

        ls_client = MagicMock()
        response = MagicMock()
        response.is_success = False
        response.text = "server error"
        ls_client.post.return_value = response

        # Should not raise, just log a warning
        _trigger_validation_task(
            ls_client=ls_client,
            circuit_id=uuid4(),
            project_id=uuid4(),
            virtual_lab_id=uuid4(),
        )
        ls_client.post.assert_called_once()

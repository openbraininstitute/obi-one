"""Integration tests for the MESH validation endpoint."""

import logging
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.endpoints.mesh_validation import (
    MAX_FILE_SIZE,
    FileTooLargeError,
    ValidationStatus,
    _cleanup_temp_file,
    _save_upload_to_tempfile,
    router as mesh_router,
    validate_mesh_reader,
)
from app.errors import ApiErrorCode

ROUTE = "/declared/test-mesh-file"
VALID_EXTENSION = ".obj"


def get_error_code(response_json: dict) -> str:
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("code")
    return response_json.get("code")


def get_error_detail(response_json: dict) -> str:
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("detail")
    return response_json.get("detail")


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mesh_router)

    def mock_user_verified():
        return True

    app.dependency_overrides[user_verified] = mock_user_verified
    return TestClient(app)


@pytest.fixture
def valid_mesh_upload() -> dict:
    return {"file": (f"valid{VALID_EXTENSION}", BytesIO(b"v 0 0 0"), "application/octet-stream")}


@pytest.fixture
def empty_mesh_upload() -> dict:
    return {"file": (f"empty{VALID_EXTENSION}", BytesIO(b""), "application/octet-stream")}


def test_validate_mesh_file_success(client, valid_mesh_upload, tmp_path):
    saved_path = None

    def fake_save(_file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        path = tmp_path / f"saved{suffix}"
        path.write_bytes(_file.file.read())
        saved_path = str(path)
        return saved_path

    mock_cleanup = MagicMock()

    with (
        patch("app.endpoints.mesh_validation._save_upload_to_tempfile", side_effect=fake_save),
        patch("app.endpoints.mesh_validation.validate_mesh_reader", return_value=None),
        patch("app.endpoints.mesh_validation._cleanup_temp_file", side_effect=mock_cleanup),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == ValidationStatus.SUCCESS
    assert response.json()["message"] == "MESH file validation successful."
    mock_cleanup.assert_called_once_with(saved_path)


def test_validate_mesh_file_invalid_extension(client):
    invalid_file = {"file": ("bad.txt", BytesIO(b"data"), "text/plain")}
    response = client.post(ROUTE, files=invalid_file)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert get_error_code(response.json()) == ApiErrorCode.INVALID_REQUEST
    assert "Invalid file extension" in get_error_detail(response.json())


def test_validate_mesh_file_empty(client, empty_mesh_upload, tmp_path):
    saved_path = str(tmp_path / "empty.obj")
    Path(saved_path).write_bytes(b"")

    with (
        patch("app.endpoints.mesh_validation._save_upload_to_tempfile", return_value=saved_path),
        patch("app.endpoints.mesh_validation._cleanup_temp_file"),
    ):
        response = client.post(ROUTE, files=empty_mesh_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "Uploaded file is empty" in get_error_detail(response.json())


def test_validate_mesh_file_too_large(client, valid_mesh_upload):
    with patch(
        "app.endpoints.mesh_validation._save_upload_to_tempfile",
        side_effect=FileTooLargeError("Too big"),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "too large" in get_error_detail(response.json()).lower()


def test_validate_mesh_file_reader_fails(client, valid_mesh_upload, tmp_path):
    saved_path = tmp_path / "fail.obj"
    saved_path.write_bytes(b"invalid data")

    with (
        patch(
            "app.endpoints.mesh_validation._save_upload_to_tempfile", return_value=str(saved_path)
        ),
        patch(
            "app.endpoints.mesh_validation.validate_mesh_reader",
            side_effect=RuntimeError("pylmesh load error"),
        ),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "MESH validation failed" in get_error_detail(response.json())
    assert not saved_path.exists()


def test_validate_mesh_file_os_error(client, valid_mesh_upload):
    with patch(
        "app.endpoints.mesh_validation._save_upload_to_tempfile", side_effect=OSError("Disk full")
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert get_error_code(response.json()) == "INTERNAL_ERROR"


def test_validate_mesh_file_background_cleanup_scheduled(client, valid_mesh_upload, tmp_path):
    saved_path = tmp_path / "test_cleanup.obj"
    saved_path.write_bytes(b"v 0 0 0")

    mock_cleanup = MagicMock()
    with (
        patch(
            "app.endpoints.mesh_validation._save_upload_to_tempfile", return_value=str(saved_path)
        ),
        patch("app.endpoints.mesh_validation.validate_mesh_reader", return_value=None),
        patch("app.endpoints.mesh_validation._cleanup_temp_file", side_effect=mock_cleanup),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == ValidationStatus.SUCCESS
    mock_cleanup.assert_called_once_with(str(saved_path))


def test_validate_mesh_file_too_large_via_size_header(client):
    large_file = {"file": (f"big{VALID_EXTENSION}", BytesIO(b"data"), "application/octet-stream")}

    with patch("app.endpoints.mesh_validation.MAX_FILE_SIZE", -1):
        response = client.post(ROUTE, files=large_file)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "too large" in get_error_detail(response.json()).lower()


def test_validate_mesh_reader_raises_on_value_error():
    with (
        patch("app.endpoints.mesh_validation.pylmesh.load_mesh", side_effect=ValueError("bad")),
        pytest.raises(ValueError, match="Failed to load OBJ file"),
    ):
        validate_mesh_reader("dummy.obj")


def test_validate_mesh_reader_raises_on_os_error():
    with (
        patch("app.endpoints.mesh_validation.pylmesh.load_mesh", side_effect=OSError("missing")),
        pytest.raises(ValueError, match="Failed to load OBJ file"),
    ):
        validate_mesh_reader("dummy.obj")


def test_validate_mesh_reader_raises_on_empty_mesh():
    mock_mesh = MagicMock()
    mock_mesh.is_empty.return_value = True

    with (
        patch("app.endpoints.mesh_validation.pylmesh.load_mesh", return_value=mock_mesh),
        pytest.raises(ValueError, match="contains no geometry"),
    ):
        validate_mesh_reader("dummy.obj")


def test_validate_mesh_reader_returns_mesh_on_success():
    mock_mesh = MagicMock()
    mock_mesh.is_empty.return_value = False

    with patch("app.endpoints.mesh_validation.pylmesh.load_mesh", return_value=mock_mesh):
        result = validate_mesh_reader("dummy.obj")

    assert result is mock_mesh


def test_save_upload_to_tempfile_exceeds_size_limit_mid_stream():
    chunk1 = b"x" * (MAX_FILE_SIZE - 10)
    chunk2 = b"x" * 20

    mock_file = MagicMock()
    mock_file.file = BytesIO(chunk1 + chunk2)

    with pytest.raises(FileTooLargeError):
        _save_upload_to_tempfile(mock_file, suffix=".obj")


def test_save_upload_to_tempfile_cleans_up_on_read_error():
    mock_file = MagicMock()
    mock_file.file.seek = MagicMock()
    mock_file.file.read = MagicMock(side_effect=OSError("read failed"))

    with pytest.raises(OSError, match="read failed"):
        _save_upload_to_tempfile(mock_file, suffix=".obj")


def test_cleanup_temp_file_os_error_is_logged(tmp_path, caplog):
    fake_path = tmp_path / "ghost.obj"
    fake_path.write_bytes(b"x")

    with (
        patch("pathlib.Path.unlink", side_effect=OSError("permission denied")),
        caplog.at_level(logging.WARNING),
    ):
        _cleanup_temp_file(str(fake_path))

    assert any("Failed to delete" in r.message for r in caplog.records)

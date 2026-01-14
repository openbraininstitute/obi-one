"""Integration tests for the MESH validation endpoint."""

from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified
from app.endpoints.mesh_validation import FileTooLargeError, router as mesh_router
from app.errors import ApiErrorCode

# -----------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------
ROUTE = "/declared/validate-mesh-file"
VALID_EXTENSION = ".obj"


# -----------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------
def get_error_code(response_json: dict) -> str:
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("code")
    return response_json.get("code")


def get_error_detail(response_json: dict) -> str:
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("detail")
    return response_json.get("detail")


# -----------------------------------------------------------------
# FIXTURES
# -----------------------------------------------------------------
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

# -----------------------------------------------------------------
# TESTS
# -----------------------------------------------------------------


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
    assert response.json()["status"] == "success"
    mock_cleanup.assert_called_once_with(saved_path)


def test_validate_mesh_file_invalid_extension(client):
    # Testing with .txt which should fail the .obj check
    invalid_file = {"file": ("bad.txt", BytesIO(b"data"), "text/plain")}
    response = client.post(ROUTE, files=invalid_file)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert get_error_code(response.json()) == ApiErrorCode.INVALID_REQUEST
    # The current code error message says ".mesh" even though it checks for ".obj"
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
    # Simulate the FileTooLargeError raised during the save process
    with patch(
        "app.endpoints.mesh_validation._save_upload_to_tempfile",
        side_effect=FileTooLargeError("Too big")
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "too large" in get_error_detail(response.json()).lower()


def test_validate_mesh_file_reader_fails(client, valid_mesh_upload, tmp_path):
    saved_path = tmp_path / "fail.obj"
    saved_path.write_bytes(b"invalid data")

    with (
        patch(
            "app.endpoints.mesh_validation._save_upload_to_tempfile",
            return_value=str(saved_path)
        ),
        patch(
            "app.endpoints.mesh_validation.validate_mesh_reader",
            side_effect=RuntimeError("Trimesh explosion")
        ),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "MESH validation failed" in get_error_detail(response.json())
    # Ensure immediate cleanup happened because of the RuntimeError catch block
    assert not saved_path.exists()


def test_validate_mesh_file_os_error(client, valid_mesh_upload):
    with patch(
        "app.endpoints.mesh_validation._save_upload_to_tempfile",
        side_effect=OSError("Disk full")
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
            "app.endpoints.mesh_validation._save_upload_to_tempfile",
            return_value=str(saved_path)
        ),
        patch("app.endpoints.mesh_validation.validate_mesh_reader", return_value=None),
        patch("app.endpoints.mesh_validation._cleanup_temp_file", side_effect=mock_cleanup),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload)

    assert response.status_code == HTTPStatus.OK
    # In a real background task, the file stays until the task runs.
    # Our mock verifies the task was added to the background queue.
    mock_cleanup.assert_called_once_with(str(saved_path))

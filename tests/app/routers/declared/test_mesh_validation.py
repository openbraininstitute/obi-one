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
    VALID_MESH_EXTENSIONS,
    FileTooLargeError,
    ValidationStatus,
    _cleanup_temp_file,
    _save_upload_to_tempfile,
    router as mesh_router,
    validate_mesh_reader,
)
from app.errors import ApiErrorCode

ROUTE = "/declared/test-mesh-file"
VALID_EXTENSIONS = sorted(VALID_MESH_EXTENSIONS)


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
def valid_mesh_upload():
    def _make(extension: str) -> dict:
        return {"file": (f"valid{extension}", BytesIO(b"mesh-data"), "application/octet-stream")}

    return _make


@pytest.fixture
def empty_mesh_upload():
    def _make(extension: str) -> dict:
        return {"file": (f"empty{extension}", BytesIO(b""), "application/octet-stream")}

    return _make


@pytest.mark.parametrize("extension", VALID_EXTENSIONS)
def test_validate_mesh_file_success(client, valid_mesh_upload, tmp_path, extension):
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
        response = client.post(ROUTE, files=valid_mesh_upload(extension))

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == ValidationStatus.SUCCESS
    assert response.json()["message"] == "MESH file validation successful."
    assert saved_path.endswith(extension)
    mock_cleanup.assert_called_once_with(saved_path)


def test_validate_mesh_file_invalid_extension(client):
    invalid_file = {"file": ("bad.txt", BytesIO(b"data"), "text/plain")}
    response = client.post(ROUTE, files=invalid_file)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert get_error_code(response.json()) == ApiErrorCode.INVALID_REQUEST
    detail = get_error_detail(response.json())
    assert "Invalid file extension" in detail
    for extension in VALID_EXTENSIONS:
        assert extension in detail


@pytest.mark.parametrize("extension", VALID_EXTENSIONS)
def test_validate_mesh_file_empty(client, empty_mesh_upload, tmp_path, extension):
    saved_path = str(tmp_path / f"empty{extension}")
    Path(saved_path).write_bytes(b"")

    with (
        patch("app.endpoints.mesh_validation._save_upload_to_tempfile", return_value=saved_path),
        patch("app.endpoints.mesh_validation._cleanup_temp_file"),
    ):
        response = client.post(ROUTE, files=empty_mesh_upload(extension))

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "Uploaded file is empty" in get_error_detail(response.json())


@pytest.mark.parametrize("extension", VALID_EXTENSIONS)
def test_validate_mesh_file_too_large(client, valid_mesh_upload, extension):
    with patch(
        "app.endpoints.mesh_validation._save_upload_to_tempfile",
        side_effect=FileTooLargeError("Too big"),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload(extension))

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "too large" in get_error_detail(response.json()).lower()


@pytest.mark.parametrize("extension", VALID_EXTENSIONS)
def test_validate_mesh_file_reader_fails(client, valid_mesh_upload, tmp_path, extension):
    saved_path = tmp_path / f"fail{extension}"
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
        response = client.post(ROUTE, files=valid_mesh_upload(extension))

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "MESH validation failed" in get_error_detail(response.json())
    assert not saved_path.exists()


@pytest.mark.parametrize("extension", VALID_EXTENSIONS)
def test_validate_mesh_file_os_error(client, valid_mesh_upload, extension):
    with patch(
        "app.endpoints.mesh_validation._save_upload_to_tempfile", side_effect=OSError("Disk full")
    ):
        response = client.post(ROUTE, files=valid_mesh_upload(extension))

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert get_error_code(response.json()) == "INTERNAL_ERROR"


@pytest.mark.parametrize("extension", VALID_EXTENSIONS)
def test_validate_mesh_file_background_cleanup_scheduled(
    client, valid_mesh_upload, tmp_path, extension
):
    saved_path = tmp_path / f"test_cleanup{extension}"
    saved_path.write_bytes(b"mesh-data")

    mock_cleanup = MagicMock()
    with (
        patch(
            "app.endpoints.mesh_validation._save_upload_to_tempfile", return_value=str(saved_path)
        ),
        patch("app.endpoints.mesh_validation.validate_mesh_reader", return_value=None),
        patch("app.endpoints.mesh_validation._cleanup_temp_file", side_effect=mock_cleanup),
    ):
        response = client.post(ROUTE, files=valid_mesh_upload(extension))

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == ValidationStatus.SUCCESS
    mock_cleanup.assert_called_once_with(str(saved_path))


@pytest.mark.parametrize("extension", VALID_EXTENSIONS)
def test_validate_mesh_file_too_large_via_size_header(client, extension):
    large_file = {"file": (f"big{extension}", BytesIO(b"data"), "application/octet-stream")}

    with patch("app.endpoints.mesh_validation.MAX_FILE_SIZE", -1):
        response = client.post(ROUTE, files=large_file)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert "too large" in get_error_detail(response.json()).lower()


def test_validate_mesh_reader_raises_on_value_error():
    with (
        patch("app.endpoints.mesh_validation.pylmesh.load_mesh", side_effect=ValueError("bad")),
        pytest.raises(ValueError, match="Failed to load MESH file"),
    ):
        validate_mesh_reader("dummy.obj")


def test_validate_mesh_reader_raises_on_os_error():
    with (
        patch("app.endpoints.mesh_validation.pylmesh.load_mesh", side_effect=OSError("missing")),
        pytest.raises(ValueError, match="Failed to load MESH file"),
    ):
        validate_mesh_reader("dummy.glb")


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
        result = validate_mesh_reader("dummy.glb")

    assert result is mock_mesh


def test_save_upload_to_tempfile_success():
    mock_file = MagicMock()
    mock_file.file = BytesIO(b"mesh-bytes")

    path = _save_upload_to_tempfile(mock_file, suffix=".obj")
    try:
        assert path.endswith(".obj")
        assert Path(path).read_bytes() == b"mesh-bytes"
    finally:
        Path(path).unlink(missing_ok=True)


def test_save_upload_to_tempfile_exceeds_size_limit_mid_stream(monkeypatch):
    # Production MAX_FILE_SIZE is 5 GiB; use ~1.5 MiB so the first 1 MiB read is
    # written and the next read crosses the limit (same mid-stream path, ~ms).
    chunk_size = 1024 * 1024
    limit = chunk_size + chunk_size // 2
    monkeypatch.setattr("app.endpoints.mesh_validation.MAX_FILE_SIZE", limit)
    chunk1 = b"x" * (limit - 10)
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
        _save_upload_to_tempfile(mock_file, suffix=".glb")


def test_save_upload_to_tempfile_cleanup_skips_missing_tempfile():
    mock_file = MagicMock()
    mock_file.file.seek = MagicMock()
    mock_file.file.read = MagicMock(side_effect=OSError("read failed"))

    with patch("app.endpoints.mesh_validation.pathlib.Path") as path_cls:
        path_inst = MagicMock()
        path_inst.exists.return_value = False
        path_cls.return_value = path_inst
        with pytest.raises(OSError, match="read failed"):
            _save_upload_to_tempfile(mock_file, suffix=".glb")
        path_inst.unlink.assert_not_called()


def test_cleanup_temp_file_os_error_is_logged(tmp_path, caplog):
    fake_path = tmp_path / "ghost.obj"
    fake_path.write_bytes(b"x")

    with (
        patch("pathlib.Path.unlink", side_effect=OSError("permission denied")),
        caplog.at_level(logging.WARNING),
    ):
        _cleanup_temp_file(str(fake_path))

    assert any("Failed to delete" in r.message for r in caplog.records)

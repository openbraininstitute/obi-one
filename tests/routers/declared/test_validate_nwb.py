"""Integration tests for the NWB validation endpoint."""

from io import BytesIO
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock, patch

import anyio
import pytest
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from http import HTTPStatus

# Import AFTER patching
from app.endpoints.nwb_validation import (
    NWBValidationResponse,
    activate_test_nwb_endpoint,
)


# -----------------------------------------------------------------
# GLOBAL FIXTURE: Patch ApiErrorCode BEFORE endpoint import
# -----------------------------------------------------------------
@pytest.fixture(autouse=True)
def patch_api_error_code():
    mock_err = MagicMock()
    mock_err.BAD_REQUEST = "BAD_REQUEST"
    with patch("app.endpoints.nwb_validation.ApiErrorCode", mock_err):
        yield


# -----------------------------------------------------------------
# Helper: the endpoint callable
# -----------------------------------------------------------------
@pytest.fixture
def endpoint() -> Callable:
    router = APIRouter()
    activate_test_nwb_endpoint(router)

    route = None
    for r in router.routes:
        if getattr(r, "path", "").endswith("/validate-nwb-file") and "POST" in r.methods:
            route = r
            break

    if route is None:
        raise AssertionError("NWB validation endpoint not registered")
    return route.endpoint


@pytest.fixture
def background_tasks() -> BackgroundTasks:
    return BackgroundTasks()


# -----------------------------------------------------------------
# Test files
# -----------------------------------------------------------------
@pytest.fixture
def valid_nwb_file() -> UploadFile:
    return UploadFile(filename="valid.nwb", file=BytesIO(b"mock-nwb-data"))


@pytest.fixture
def empty_nwb_file() -> UploadFile:
    return UploadFile(filename="empty.nwb", file=BytesIO(b""))


# -----------------------------------------------------------------
# 1. SUCCESS
# -----------------------------------------------------------------
def test_validate_nwb_file_success(
    endpoint,
    valid_nwb_file: UploadFile,
    background_tasks: BackgroundTasks,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        content = file.file.read()
        path = tmp_path / f"saved{suffix}"
        path.write_bytes(content)
        saved_path = str(path)
        return saved_path

    def fake_cleanup(path: str) -> None:
        p = Path(path)
        if p.exists():
            p.unlink()

    with patch(
        "app.endpoints.nwb_validation._save_upload_to_tempfile",
        side_effect=fake_save,
    ), patch(
        "app.endpoints.nwb_validation.validate_all_nwb_readers",
        return_value=None,
    ), patch(
        "app.endpoints.nwb_validation._cleanup_temp_file",
        side_effect=fake_cleanup,
    ):
        resp: NWBValidationResponse = endpoint(valid_nwb_file, background_tasks)

    assert resp.status == "success"
    assert resp.message == "NWB file validation successful."

    anyio.run(background_tasks)
    assert not any(tmp_path.glob("saved*"))


# -----------------------------------------------------------------
# 2. CLIENT ERRORS (400)
# -----------------------------------------------------------------
def test_validate_nwb_file_invalid_extension(endpoint, background_tasks: BackgroundTasks):
    file = UploadFile(filename="bad.txt", file=BytesIO(b"data"))

    with pytest.raises(HTTPException) as exc:
        endpoint(file, background_tasks)

    assert exc.value.status_code == 400
    assert "extension" in exc.value.detail["detail"].lower()


def test_validate_nwb_file_empty(
    endpoint,
    empty_nwb_file: UploadFile,
    background_tasks: BackgroundTasks,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        path = tmp_path / f"empty{suffix}"
        path.write_bytes(b"")
        saved_path = str(path)
        return saved_path

    def fake_handle_empty(upload_file: UploadFile) -> None:
        from app.logger import L
        L.error(f"Empty file uploaded: {upload_file.filename}")
        if saved_path and Path(saved_path).exists():
            Path(saved_path).unlink()
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": "BAD_REQUEST",  # real code uses ApiErrorCode.BAD_REQUEST
                "detail": "Uploaded file is empty",
            },
        )

    with patch(
        "app.endpoints.nwb_validation._save_upload_to_tempfile",
        side_effect=fake_save,
    ), patch(
        "app.endpoints.nwb_validation._handle_empty_file",
        side_effect=fake_handle_empty,
    ), patch(
        "app.endpoints.nwb_validation.validate_all_nwb_readers"
    ) as mock_validate:
        with pytest.raises(HTTPException) as exc:
            endpoint(empty_nwb_file, background_tasks)

    assert exc.value.status_code == 400
    assert "empty" in exc.value.detail["detail"].lower()
    mock_validate.assert_not_called()
    assert saved_path is not None
    assert not Path(saved_path).exists()


def test_validate_nwb_file_no_filename(endpoint, background_tasks: BackgroundTasks):
    file = UploadFile(filename="", file=BytesIO(b"data"))

    with pytest.raises(HTTPException) as exc:
        endpoint(file, background_tasks)

    assert exc.value.status_code == 400
    assert "extension" in exc.value.detail["detail"].lower()


# -----------------------------------------------------------------
# 3. READER FAILS → 400
# -----------------------------------------------------------------
def test_validate_nwb_file_reader_fails(
    endpoint,
    valid_nwb_file: UploadFile,
    background_tasks: BackgroundTasks,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        content = file.file.read()
        path = tmp_path / f"fail{suffix}"
        path.write_bytes(content)
        saved_path = str(path)
        return saved_path

    with patch(
        "app.endpoints.nwb_validation._save_upload_to_tempfile",
        side_effect=fake_save,
    ), patch(
        "app.endpoints.nwb_validation.validate_all_nwb_readers",
        side_effect=RuntimeError("All NWB readers failed."),
    ):
        with pytest.raises(HTTPException) as exc:
            endpoint(valid_nwb_file, background_tasks)

    assert exc.value.status_code == 400
    assert "validation failed" in exc.value.detail["detail"].lower()
    assert saved_path is not None
    assert not Path(saved_path).exists()


# -----------------------------------------------------------------
# 4. SERVER ERROR → 500
# -----------------------------------------------------------------
def test_validate_nwb_file_os_error(endpoint, valid_nwb_file: UploadFile, background_tasks: BackgroundTasks):
    with patch(
        "app.endpoints.nwb_validation._save_upload_to_tempfile",
        side_effect=OSError("disk full"),
    ):
        with pytest.raises(HTTPException) as exc:
            endpoint(valid_nwb_file, background_tasks)

    assert exc.value.status_code == 500


# -----------------------------------------------------------------
# 5. CLEAN-UP ON EXCEPTION
# -----------------------------------------------------------------
def test_validate_nwb_file_cleanup_on_error(
    endpoint,
    valid_nwb_file: UploadFile,
    background_tasks: BackgroundTasks,
    tmp_path: Path,
):
    saved_path = tmp_path / "cleanup.nwb"

    def fake_save(file: UploadFile, suffix: str) -> str:
        content = file.file.read()
        saved_path.write_bytes(content)
        return str(saved_path)

    with patch(
        "app.endpoints.nwb_validation._save_upload_to_tempfile",
        side_effect=fake_save,
    ), patch(
        "app.endpoints.nwb_validation.validate_all_nwb_readers",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(HTTPException):
            endpoint(valid_nwb_file, background_tasks)

    assert not saved_path.exists()


# -----------------------------------------------------------------
# 6. REAL READER (mocked import)
# -----------------------------------------------------------------
def test_validate_nwb_file_real_reader_success(
    endpoint,
    valid_nwb_file: UploadFile,
    background_tasks: BackgroundTasks,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        content = file.file.read()
        path = tmp_path / f"real{suffix}"
        path.write_bytes(content)
        saved_path = str(path)
        return saved_path

    fake_reader = MagicMock()
    fake_reader_instance = MagicMock()
    fake_reader_instance.read.return_value = {"mock": "data"}
    fake_reader.return_value = fake_reader_instance

    def fake_cleanup(path: str) -> None:
        p = Path(path)
        if p.exists():
            p.unlink()

    with patch(
        "app.endpoints.nwb_validation._save_upload_to_tempfile",
        side_effect=fake_save,
    ), patch(
        "app.endpoints.nwb_validation._cleanup_temp_file",
        side_effect=fake_cleanup,
    ), patch(
        "bluepyefe.reader.AIBSNWBReader", fake_reader
    ), patch(
        "bluepyefe.reader.BBPNWBReader", MagicMock()
    ), patch(
        "bluepyefe.reader.ScalaNWBReader", MagicMock()
    ), patch(
        "bluepyefe.reader.TRTNWBReader", MagicMock()
    ):
        resp: NWBValidationResponse = endpoint(valid_nwb_file, background_tasks)

    assert resp.status == "success"
    assert resp.message == "NWB file validation successful."

    anyio.run(background_tasks)
    assert not any(tmp_path.glob("real*"))


# -----------------------------------------------------------------
# 7. BACKGROUND TASK CLEANUP
# -----------------------------------------------------------------
def test_validate_nwb_file_background_cleanup(
    endpoint,
    valid_nwb_file: UploadFile,
    background_tasks: BackgroundTasks,
    tmp_path: Path,
):
    saved_path = tmp_path / "background.nwb"

    def fake_save(file: UploadFile, suffix: str) -> str:
        content = file.file.read()
        saved_path.write_bytes(content)
        return str(saved_path)

    def fake_cleanup(path: str) -> None:
        p = Path(path)
        if p.exists():
            p.unlink()

    with patch(
        "app.endpoints.nwb_validation._save_upload_to_tempfile",
        side_effect=fake_save,
    ), patch(
        "app.endpoints.nwb_validation.validate_all_nwb_readers",
        return_value=None,
    ), patch(
        "app.endpoints.nwb_validation._cleanup_temp_file",
        side_effect=fake_cleanup,
    ):
        resp = endpoint(valid_nwb_file, background_tasks)

        assert saved_path.exists()
        anyio.run(background_tasks)
        assert not saved_path.exists()

    assert resp.status == "success"
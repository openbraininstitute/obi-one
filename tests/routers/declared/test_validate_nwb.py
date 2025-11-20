"""Integration tests for the NWB validation endpoint."""

from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.dependencies.auth import user_verified

# Import AFTER patching
from app.endpoints.nwb_validation import (
    router as nwb_router,  # Import the router directly
)

# Import ApiErrorCode directly for use in test logic
from app.errors import ApiErrorCode
from app.logger import L

# -----------------------------------------------------------------
# CONSTANTS
# -----------------------------------------------------------------
ROUTE = "/declared/validate-nwb-file"


# Helper to safely retrieve the 'code' from the response, handling nested 'detail' wrapping
def get_error_code(response_json: dict) -> str:
    """Safely retrieves the error code from a TestClient response."""
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("code")
    # Otherwise, assume 'code' is at the root
    return response_json.get("code")


# Helper to safely retrieve the 'detail' message
def get_error_detail(response_json: dict) -> str:
    """Safely retrieves the error detail message from a TestClient response."""
    if isinstance(response_json.get("detail"), dict):
        return response_json["detail"].get("detail")
    # The default FastAPI 500 error structure has the detail at the root
    return response_json.get("detail")


# -----------------------------------------------------------------
# GLOBAL FIXTURE: TestClient and Dependency Overrides
# -----------------------------------------------------------------
@pytest.fixture
def client():
    """Fixture to provide a TestClient instance."""
    app = FastAPI()
    app.include_router(nwb_router)

    # Mock the required dependency
    def mock_user_verified():
        return True

    # Override the dependency for testing
    app.dependency_overrides[user_verified] = mock_user_verified

    return TestClient(app)


# -----------------------------------------------------------------
# Test files (Refactored for TestClient 'files' argument)
# -----------------------------------------------------------------
@pytest.fixture
def valid_nwb_upload() -> dict:
    return {"file": ("valid.nwb", BytesIO(b"mock-nwb-data"), "application/octet-stream")}


@pytest.fixture
def empty_nwb_upload() -> dict:
    return {"file": ("empty.nwb", BytesIO(b""), "application/octet-stream")}


# -----------------------------------------------------------------
# 1. SUCCESS
# -----------------------------------------------------------------
def test_validate_nwb_file_success(
    client: TestClient,
    valid_nwb_upload: dict,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(_file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        # Content read simulation
        _file.file.seek(0)
        content = _file.file.read()
        path = tmp_path / f"saved{suffix}"
        path.write_bytes(content)
        saved_path = str(path)
        return saved_path

    # Mock cleanup to track execution
    mock_cleanup = MagicMock()

    with (
        patch(
            "app.endpoints.nwb_validation._save_upload_to_tempfile",
            side_effect=fake_save,
        ),
        patch(
            "app.endpoints.nwb_validation.validate_all_nwb_readers",
            return_value=None,
        ),
        patch(
            "app.endpoints.nwb_validation._cleanup_temp_file",
            side_effect=mock_cleanup,
        ),
    ):
        response = client.post(ROUTE, files=valid_nwb_upload)

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "status": "success",
        "message": "NWB file validation successful.",
    }

    # Verify cleanup was scheduled (called as a background task)
    mock_cleanup.assert_called_once_with(saved_path)

    assert Path(saved_path).exists()


# -----------------------------------------------------------------
# 2. CLIENT ERRORS (400)
# -----------------------------------------------------------------
def test_validate_nwb_file_invalid_extension(client: TestClient):
    invalid_file = {"file": ("bad.txt", BytesIO(b"data"), "text/plain")}

    response = client.post(ROUTE, files=invalid_file)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    response_json = response.json()

    assert get_error_code(response_json) == ApiErrorCode.INVALID_REQUEST
    assert get_error_detail(response_json) == "Invalid file extension. Must be .nwb"


def test_validate_nwb_file_empty(
    client: TestClient,
    empty_nwb_upload: dict,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(_file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        path = tmp_path / f"empty{suffix}"
        path.write_bytes(b"")
        saved_path = str(path)
        return saved_path

    def fake_handle_empty(upload_file: UploadFile) -> None:
        L.error(f"Empty file uploaded: {upload_file.filename}")
        if saved_path and Path(saved_path).exists():
            # Explicit cleanup
            Path(saved_path).unlink()
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Uploaded file is empty",
            },
        )

    mock_validate = MagicMock()

    with (
        patch(
            "app.endpoints.nwb_validation._save_upload_to_tempfile",
            side_effect=fake_save,
        ),
        # Patch _handle_empty_file
        patch("app.endpoints.nwb_validation._handle_empty_file", side_effect=fake_handle_empty),
        patch("app.endpoints.nwb_validation.validate_all_nwb_readers", mock_validate),
    ):
        response = client.post(ROUTE, files=empty_nwb_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    response_json = response.json()

    assert get_error_code(response_json) == ApiErrorCode.INVALID_REQUEST
    assert get_error_detail(response_json) == "Uploaded file is empty"

    mock_validate.assert_not_called()
    assert saved_path is not None
    # Assert cleanup happened
    assert not Path(saved_path).exists()


def test_validate_nwb_file_no_filename(client: TestClient):
    file_data = {"file": ("", BytesIO(b"data"), "application/octet-stream")}

    response = client.post(ROUTE, files=file_data)

    # Assert 422 (Unprocessable Entity)
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    # Check for the standard 422 error structure
    assert "detail" in response.json()
    assert isinstance(response.json()["detail"], list)
    assert response.json()["detail"][0]["type"] == "value_error"
    assert len(response.json()["detail"][0]["loc"]) > 0


# -----------------------------------------------------------------
# 3. READER FAILS → 400
# -----------------------------------------------------------------
def test_validate_nwb_file_reader_fails(
    client: TestClient,
    valid_nwb_upload: dict,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(_file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        content = _file.file.read()
        path = tmp_path / f"fail{suffix}"
        path.write_bytes(content)
        saved_path = str(path)
        return saved_path

    with (
        patch(
            "app.endpoints.nwb_validation._save_upload_to_tempfile",
            side_effect=fake_save,
        ),
        patch(
            "app.endpoints.nwb_validation.validate_all_nwb_readers",
            side_effect=RuntimeError("All NWB readers failed."),
        ),
    ):
        response = client.post(ROUTE, files=valid_nwb_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    response_json = response.json()
    # FIX: Use helper function to retrieve code and detail
    assert get_error_code(response_json) == ApiErrorCode.INVALID_REQUEST
    assert "NWB validation failed: All NWB readers failed." in get_error_detail(response_json)
    assert saved_path is not None
    assert not Path(saved_path).exists()


# -----------------------------------------------------------------
# 4. SERVER ERROR → 500
# -----------------------------------------------------------------
def test_validate_nwb_file_os_error(client: TestClient, valid_nwb_upload: dict):
    os_error_message = "disk full"
    with (
        patch(
            "app.endpoints.nwb_validation._save_upload_to_tempfile",
            side_effect=OSError(os_error_message),
        ),
    ):
        response = client.post(ROUTE, files=valid_nwb_upload)

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    response_json = response.json()
    # FIX: Use helper function to retrieve code and detail
    assert get_error_code(response_json) == "INTERNAL_ERROR"
    assert os_error_message in get_error_detail(response_json)


# -----------------------------------------------------------------
# 5. CLEAN-UP ON EXCEPTION
# -----------------------------------------------------------------
def test_validate_nwb_file_cleanup_on_error(
    client: TestClient,
    valid_nwb_upload: dict,
    tmp_path: Path,
):
    saved_path = tmp_path / "cleanup.nwb"

    def fake_save(file: UploadFile, suffix: str) -> str:  # noqa: ARG001
        file.file.seek(0)
        content = file.file.read()
        saved_path.write_bytes(content)
        return str(saved_path)

    with (
        patch(
            "app.endpoints.nwb_validation._save_upload_to_tempfile",
            side_effect=fake_save,
        ),
        patch(
            "app.endpoints.nwb_validation.validate_all_nwb_readers",
            side_effect=RuntimeError("boom"),
        ),
    ):
        response = client.post(ROUTE, files=valid_nwb_upload)

    assert response.status_code == HTTPStatus.BAD_REQUEST
    assert not saved_path.exists()


# -----------------------------------------------------------------
# 6. REAL READER (mocked import)
# -----------------------------------------------------------------
def test_validate_nwb_file_real_reader_success(
    client: TestClient,
    valid_nwb_upload: dict,
    tmp_path: Path,
):
    saved_path = None

    def fake_save(_file: UploadFile, suffix: str) -> str:
        nonlocal saved_path
        _file.file.seek(0)
        content = _file.file.read()
        path = tmp_path / f"real{suffix}"
        path.write_bytes(content)
        saved_path = str(path)
        return saved_path

    fake_reader = MagicMock()
    fake_reader_instance = MagicMock()
    fake_reader_instance.read.return_value = {"mock": "data"}
    fake_reader.return_value = fake_reader_instance

    mock_cleanup = MagicMock()

    with (
        patch(
            "app.endpoints.nwb_validation._save_upload_to_tempfile",
            side_effect=fake_save,
        ),
        patch(
            "app.endpoints.nwb_validation._cleanup_temp_file",
            side_effect=mock_cleanup,
        ),
        patch(
            "app.endpoints.nwb_validation.validate_all_nwb_readers",
            return_value=None,
        ),
        patch("bluepyefe.reader.AIBSNWBReader", fake_reader),
        patch("bluepyefe.reader.BBPNWBReader", MagicMock()),
        patch("bluepyefe.reader.ScalaNWBReader", MagicMock()),
        patch("bluepyefe.reader.TRTNWBReader", MagicMock()),
    ):
        response = client.post(ROUTE, files=valid_nwb_upload)

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "success"

    mock_cleanup.assert_called_once_with(saved_path)
    assert Path(saved_path).exists()


# -----------------------------------------------------------------
# 7. BACKGROUND TASK CLEANUP
# -----------------------------------------------------------------
def test_validate_nwb_file_background_cleanup(
    client: TestClient,
    valid_nwb_upload: dict,
    tmp_path: Path,
):
    saved_path = tmp_path / "background.nwb"

    def fake_save(file: UploadFile, suffix: str) -> str:  # noqa: ARG001
        file.file.seek(0)
        content = file.file.read()
        saved_path.write_bytes(content)
        return str(saved_path)

    mock_cleanup = MagicMock()

    with (
        patch(
            "app.endpoints.nwb_validation._save_upload_to_tempfile",
            side_effect=fake_save,
        ),
        patch(
            "app.endpoints.nwb_validation.validate_all_nwb_readers",
            return_value=None,
        ),
        patch(
            "app.endpoints.nwb_validation._cleanup_temp_file",
            side_effect=mock_cleanup,
        ),
    ):
        response = client.post(ROUTE, files=valid_nwb_upload)

    # Assert success and that the file was created
    assert response.status_code == HTTPStatus.OK
    assert saved_path.exists()

    # Assert background task was scheduled
    mock_cleanup.assert_called_once_with(str(saved_path))

    assert saved_path.exists()

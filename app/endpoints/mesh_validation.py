import pathlib
import tempfile
from enum import StrEnum
from http import HTTPStatus
from typing import Annotated, NoReturn

import pyvista as pv
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.errors import ApiErrorCode
from app.logger import L

# --------------------------------------------

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

# Max file size: 5 GB
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024


class ValidationStatus(StrEnum):
    """Enumeration of possible validation outcomes."""
    SUCCESS = "success"
    FAILURE = "failure"


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the maximum allowed size."""


def _handle_empty_geometry(path: str) -> NoReturn:
    """Helper to raise ValueError for empty geometry."""
    msg = f"The file '{path}' contains no geometry or is corrupted."
    raise ValueError(msg)


def _handle_mesh_load_error(error: Exception) -> NoReturn:
    """Helper to raise ValueError for mesh loading failures."""
    msg = f"Failed to load OBJ file with PyVista: {error}"
    raise ValueError(msg) from error


def validate_mesh_reader(mesh_file_path: str) -> pv.DataSet:
    """Try PyVista reader to validate the mesh file."""
    try:
        # pyvista.read handles various formats including OBJ
        mesh = pv.read(mesh_file_path)
    except (ValueError, RuntimeError, Exception) as e:
        # Catch PyVista/VTK specific loading errors
        _handle_mesh_load_error(e)
    else:
        # PyVista meshes don't have 'is_empty'; we check point/cell counts
        if mesh.n_points == 0 or mesh.n_cells == 0:
            _handle_empty_geometry(mesh_file_path)

        return mesh


class MESHValidationResponse(BaseModel):
    """Schema for the MESH file validation success response."""

    status: ValidationStatus
    message: str


# -------------------------------------------------------------------------------------------------


def _handle_empty_file(file: UploadFile) -> NoReturn:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    msg = "Uploaded file is empty"
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.INVALID_REQUEST,
            "detail": msg,
        },
    )


def _handle_file_too_large() -> NoReturn:
    """Handles cleanup and raises error when file size limit exceeded."""
    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    msg = f"File size exceeds the limit of {max_mb:.0f} MB"
    raise FileTooLargeError(msg)


def _save_upload_to_tempfile(file: UploadFile, suffix: str) -> str:
    """Save UploadFile to a temporary file synchronously."""
    chunk_size = 1024 * 1024  # 1 MB
    total_size = 0  # Track total size written

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_path = temp_file.name

        try:
            file.file.seek(0)  # Reset pointer
            while True:
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break

                chunk_len = len(chunk)
                total_size += chunk_len

                if total_size > MAX_FILE_SIZE:
                    _handle_file_too_large()

                temp_file.write(chunk)
        except Exception:
            if pathlib.Path(temp_path).exists():
                pathlib.Path(temp_path).unlink(missing_ok=True)
            raise
        else:
            return temp_path


def _cleanup_temp_file(temp_path: str) -> None:
    """Background task or immediate cleanup utility to clean up temporary file."""
    if temp_path and pathlib.Path(temp_path).exists():
        try:
            pathlib.Path(temp_path).unlink()
            L.debug(f"Cleaned up temp file: {temp_path}")
        except OSError as e:
            L.warning(f"Failed to delete temp MESH file: {e}")


def validate_mesh_file(
    file: Annotated[UploadFile, File(description="MESH file to upload (.obj)")],
    background_tasks: BackgroundTasks,
) -> MESHValidationResponse:
    """Validates an uploaded .obj file using PyVista."""
    file_extension = pathlib.Path(file.filename).suffix.lower() if file.filename else ""
    if file_extension != ".obj":
        msg = "Invalid file extension. Must be .obj"
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": msg,
            },
        )

    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        log_msg = f"MESH upload failed: File too large (Max: {max_mb:.0f} MB)"
        L.error(log_msg)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        )

    temp_file_path = ""

    try:
        temp_file_path = _save_upload_to_tempfile(file, suffix=".obj")

        if pathlib.Path(temp_file_path).stat().st_size == 0:
            _handle_empty_file(file)

        # PyVista validation
        validate_mesh_reader(temp_file_path)

        background_tasks.add_task(_cleanup_temp_file, temp_file_path)

        return MESHValidationResponse(
            status=ValidationStatus.SUCCESS,
            message="MESH file validation successful.",
        )

    except FileTooLargeError:
        L.error(f"MESH upload failed: File too large (Max: {max_mb:.0f} MB)")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        ) from None

    except (RuntimeError, ValueError) as e:
        L.error(f"MESH validation failed: {e!s}")
        _cleanup_temp_file(temp_file_path)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"MESH validation failed: {e!s}",
            },
        ) from e
    except OSError as e:
        L.error(f"File system error during MESH validation: {e!s}")
        _cleanup_temp_file(temp_file_path)
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "detail": f"Internal Server Error: {e!s}"},
        ) from e


def activate_test_mesh_endpoint(router: APIRouter) -> None:
    """Define MESH file validation endpoint."""
    router.post(
        "/test-mesh-file",
        summary="Validate MESH file format for OBP.",
        description="Validates an uploaded .obj file using PyVista.",
    )(validate_mesh_file)


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_test_mesh_endpoint(router)
    return router


router = activate_declared_endpoints(router)

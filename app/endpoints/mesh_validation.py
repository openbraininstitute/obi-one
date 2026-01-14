import pathlib
import tempfile
import trimesh
from http import HTTPStatus
from typing import Annotated, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.errors import ApiErrorCode
from app.logger import L

# --------------------------------------------

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

# Max file size: 150 MB
MAX_FILE_SIZE = 150 * 1024 * 1024


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the maximum allowed size."""


def validate_mesh_reader(mesh_file_path: str) -> None:
    """Try all MESH readers. Succeed if at least one works."""
    #read the obj and

    try:
        # trimesh.load can return a Trimesh object or a Scene (if multiple objects exist)
        mesh = trimesh.load(mesh_file_path, file_type='obj')

        # Check if the loaded object actually contains geometry
        if mesh.is_empty:
            raise ValueError(f"The file '{file_path}' contains no geometry or is corrupted.")

        return mesh

    except Exception as e:
        # Catch library-specific loading errors and re-raise them clearly
        raise ValueError(f"Failed to load OBJ file: {e}")
    
    raise RuntimeError("cannot read obj")


class MESHValidationResponse(BaseModel):
    """Schema for the MESH file validation success response."""

    status: str
    message: str


# -------------------------------------------------------------------------------------------------


def _handle_empty_file(file: UploadFile) -> NoReturn:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.INVALID_REQUEST,
            "detail": "Uploaded file is empty",
        },
    )


# Helper function to abstract the raise statement
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
                # Use chunk_size
                chunk = file.file.read(chunk_size)
                if not chunk:
                    break

                chunk_len = len(chunk)
                total_size += chunk_len

                # Check size limit before writing
                if total_size > MAX_FILE_SIZE:
                    _handle_file_too_large()

                temp_file.write(chunk)
        except Exception:
            # Cleanup for any exception during reading/writing
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
    file: Annotated[UploadFile, File(description="MESH file to upload (.mesh)")],
    background_tasks: BackgroundTasks,
) -> MESHValidationResponse:
    """Validates an uploaded .mesh file using registered readers."""
    file_extension = pathlib.Path(file.filename).suffix.lower() if file.filename else ""
    if file_extension != ".obj":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid file extension. Must be .mesh",
            },
        )

    # --- FAIL-FAST FILE SIZE CHECK ---
    # Check if file size is available and exceeds the maximum limit (150 MB)
    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        L.error(f"MESH upload failed: File too large (Max: {max_mb:.0f} MB) based on file.size.")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        )
    # ---------------------------------

    temp_file_path = ""

    try:
        # Save upload synchronously
        temp_file_path = _save_upload_to_tempfile(file, suffix=".mesh")

        if pathlib.Path(temp_file_path).stat().st_size == 0:
            _handle_empty_file(file)

        # Validate the file synchronously
        validate_mesh_reader(temp_file_path)

        # Schedule cleanup as a background task
        background_tasks.add_task(_cleanup_temp_file, temp_file_path)

        return MESHValidationResponse(
            status="success",
            message="MESH file validation successful.",
        )

    except FileTooLargeError:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        L.error(f"MESH upload failed: File too large (Max: {max_mb:.0f} MB)")
        # Cleanup is handled inside _save_upload_to_tempfile
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        ) from None

    except RuntimeError as e:
        L.error(f"MESH validation failed: {e!s}")
        # Clean up immediately on error - calling helper
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
        # Clean up immediately on error - calling helper
        _cleanup_temp_file(temp_file_path)

        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "detail": f"Internal Server Error: {e!s}"},
        ) from e


def activate_test_mesh_endpoint(router: APIRouter) -> None:
    """Define MESH file validation endpoint."""
    router.post(
        "/validate-mesh-file",
        summary="Validate MESH file format for OBP.",
        description="Validates an uploaded .mesh file using registered readers.",
    )(validate_mesh_file)


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_test_mesh_endpoint(router)
    return router


router = activate_declared_endpoints(router)

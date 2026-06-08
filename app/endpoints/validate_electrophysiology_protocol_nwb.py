import pathlib
import tempfile
from http import HTTPStatus
from typing import Annotated, Any, NoReturn
from uuid import UUID

import entitysdk.client
import numpy as np
from entitysdk.models import ElectricalCellRecording
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.dependencies.auth import user_verified
from app.dependencies.entitysdk import get_client
from app.errors import ApiErrorCode
from app.logger import L

# --------------------------------------------

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

# Max file size: 150 MB
MAX_FILE_SIZE = 150 * 1024 * 1024


class FileTooLargeError(Exception):
    """Raised when an uploaded file exceeds the maximum allowed size."""


def inspect_nwb_file_contents(nwb_file_path: str) -> dict[str, Any]:
    """Inspect an NWB file using BluePyEfe's automatic reader detection."""
    from bluepyefe.reader import inspect_nwb  # noqa: PLC0415

    return inspect_nwb(nwb_file_path)


def validate_all_nwb_readers(nwb_file_path: str) -> None:
    """Validate an NWB file using BluePyEfe's automatic reader detection."""
    inspect_nwb_file_contents(nwb_file_path)


class NWBValidationResponse(BaseModel):
    """Schema for the NWB file validation success response."""

    status: str
    message: str


class NWBInspectionResponse(BaseModel):
    """Schema for the NWB file inspection response."""

    reader: str
    protocols: list[str]
    trace_count: int
    traces: list[dict[str, Any]]
    metadata: dict[str, Any]


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
            L.warning(f"Failed to delete temp NWB file: {e}")


def _validate_nwb_upload(file: UploadFile) -> None:
    """Validate the NWB filename and declared file size."""
    file_extension = pathlib.Path(file.filename).suffix.lower() if file.filename else ""
    if file_extension != ".nwb":
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "Invalid file extension. Must be .nwb",
            },
        )

    max_mb = MAX_FILE_SIZE / (1024 * 1024)
    if file.size is not None and file.size > MAX_FILE_SIZE:
        L.error(f"NWB upload failed: File too large (Max: {max_mb:.0f} MB) based on file.size.")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        )


def _make_json_compatible(value: Any) -> Any:
    """Convert NumPy-backed BluePyEfe results to JSON-compatible values."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: _make_json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_json_compatible(item) for item in value]
    return value


def validate_nwb_file(
    file: Annotated[UploadFile, File(description="NWB file to upload (.nwb)")],
    background_tasks: BackgroundTasks,
) -> NWBValidationResponse:
    """Validates an uploaded .nwb file using registered readers."""
    _validate_nwb_upload(file)

    temp_file_path = ""

    try:
        # Save upload synchronously
        temp_file_path = _save_upload_to_tempfile(file, suffix=".nwb")

        if pathlib.Path(temp_file_path).stat().st_size == 0:
            _handle_empty_file(file)

        # Validate the file synchronously
        validate_all_nwb_readers(temp_file_path)

        # Schedule cleanup as a background task
        background_tasks.add_task(_cleanup_temp_file, temp_file_path)

        return NWBValidationResponse(
            status="success",
            message="NWB file validation successful.",
        )

    except FileTooLargeError:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        L.error(f"NWB upload failed: File too large (Max: {max_mb:.0f} MB)")
        # Cleanup is handled inside _save_upload_to_tempfile
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Uploaded file is too large. Max size: {max_mb:.0f} MB.",
            },
        ) from None

    except RuntimeError as e:
        L.error(f"NWB validation failed: {e!s}")
        # Clean up immediately on error - calling helper
        _cleanup_temp_file(temp_file_path)

        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"NWB validation failed: {e!s}",
            },
        ) from e
    except OSError as e:
        L.error(f"File system error during NWB validation: {e!s}")
        # Clean up immediately on error - calling helper
        _cleanup_temp_file(temp_file_path)

        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "detail": f"Internal Server Error: {e!s}"},
        ) from e


def inspect_electrophysiologyrecording(
    recording_id: UUID,
    db_client: Annotated[entitysdk.client.Client, Depends(get_client)],
) -> NWBInspectionResponse:
    """Parse the NWB asset of an electrical cell recording entity."""
    recording = db_client.get_entity(
        entity_id=recording_id,
        entity_type=ElectricalCellRecording,
    )
    asset = next(
        (asset for asset in recording.assets if asset.content_type == "application/nwb"),
        None,
    )
    if asset is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": (
                    f"No asset with content type 'application/nwb' found "
                    f"for recording {recording_id}."
                ),
            },
        )
    if asset.id is None:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "NWB asset is missing an id",
            },
        )

    content = db_client.download_content(
        entity_id=recording_id,
        entity_type=ElectricalCellRecording,
        asset_id=asset.id,
    )
    try:
        with tempfile.NamedTemporaryFile(suffix=".nwb") as temp_file:
            temp_file.write(content)
            temp_file.flush()
            result = _make_json_compatible(inspect_nwb_file_contents(temp_file.name))
        return NWBInspectionResponse(
            reader=result["reader"],
            protocols=result["protocols"],
            trace_count=len(result["traces"]),
            traces=result["traces"],
            metadata=result["metadata"],
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"NWB inspection failed: {e!s}",
            },
        ) from e
    except OSError as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={"code": "INTERNAL_ERROR", "detail": f"Internal Server Error: {e!s}"},
        ) from e


def activate_test_nwb_endpoint(router: APIRouter) -> None:
    """Define NWB file validation endpoint."""
    router.post(
        "/validate-electrophysiology-protocol-nwb-file",
        summary="Validate NWB file format for OBP.",
        description="Validates an uploaded .nwb file using registered readers.",
    )(validate_nwb_file)


def activate_inspect_nwb_endpoint(router: APIRouter) -> None:
    """Define NWB file inspection endpoint."""
    router.get(
        "/electrophysiologyrecording-inspection/{recording_id}",
        summary="Inspect electrical cell recording NWB traces and metadata.",
        description=(
            "Downloads and parses the NWB asset of an electrical cell recording entity "
            "using BluePyEfe automatic reader detection."
        ),
    )(inspect_electrophysiologyrecording)


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_test_nwb_endpoint(router)
    activate_inspect_nwb_endpoint(router)
    return router


router = activate_declared_endpoints(router)

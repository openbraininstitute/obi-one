import pathlib
import tempfile
from http import HTTPStatus
from typing import Annotated
import asyncio
import functools # Needed for partial in some asyncio use cases, though not strictly required for to_thread here.

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.errors import (
    ApiErrorCode,
)
from app.logger import L
import subprocess # Retained for subprocess.run, but we wrap it.


def _handle_empty_file(file: UploadFile) -> None:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.BAD_REQUEST,
            "detail": "Uploaded file is empty",
        },
    )


async def _process_nwb(file: UploadFile, temp_file_path: str) -> None:
    """Validate nwb file with pynwb."""
    # Use asyncio.to_thread to run the blocking subprocess.run in a separate thread
    # to avoid blocking the main event loop (Fixes ASYNC221).
    # The command is defined as a list, and temp_file_path is internally generated,
    # mitigating risks flagged by S404 and S603.
    command = ["pynwb-validate", temp_file_path]
    
    # Define the blocking function call
    def blocking_validation():
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            # shell=False is the default and is safer; using the list form avoids shell=True issues
        )

    try:
        # Run the blocking call in a thread pool
        await asyncio.to_thread(blocking_validation)
    except subprocess.CalledProcessError as e:
        # Handle validation failures explicitly
        error_output = e.stderr or e.stdout or "Validation failed."
        L.error(f"Nwb validation failed for file {file.filename}: {error_output}")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"NWB validation failed: {error_output.strip()}",
            },
        ) from e
    except Exception as e:
        L.error(f"Nwb error validating file {file.filename}: {e!s}")
        # Catch other exceptions like FileNotFoundError
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"Failed to run validation tool: {e!s}",
            },
        ) from e
    else:
        return


async def _validate_and_read_nwb_file(file: UploadFile) -> tuple[bytes, str]:
    """Validates file extension and reads content."""
    L.info(f"Received file upload: {file.filename}")
    allowed_extensions = {".nwb"}
    file_extension = f".{file.filename.split('.')[-1].lower()}" if file.filename else ""

    if not file.filename or file_extension not in allowed_extensions:
        L.error(f"Invalid file extension: {file_extension}")
        valid_extensions = ", ".join(allowed_extensions)
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"Invalid file extension. Must be one of {valid_extensions}",
            },
        )

    content = await file.read()
    if not content:
        _handle_empty_file(file)

    return content, file_extension


def activate_test_nwb_endpoint(router: APIRouter) -> None:
    """Define neuron file test endpoint."""

    @router.post(
        "/test-nwb-file",
        summary="Validate new format.",
        description="Tests a new file (.nwb) with basic validation.",
    )
    async def test_nwb_file(
        file: Annotated[UploadFile, File(description="Nwb file to upload (.swc, .h5, or .asc)")],
    ) -> FileResponse:
        content, file_extension = await _validate_and_read_nwb_file(file)

        temp_file_path = ""

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(content)
                temp_file_path = temp_file.name
            await _process_nwb(
                file=file, temp_file_path=temp_file_path
            )
            return
        finally:
            if temp_file_path:
                try:
                    pathlib.Path(temp_file_path).unlink(missing_ok=True)
                except OSError as e:
                    L.error(f"Error deleting temporary files: {e!s}")


def activate_declared_endpoints(router: APIRouter) -> APIRouter:
    """Activate all declared endpoints for the router."""
    activate_test_nwb_endpoint(router)
    return router

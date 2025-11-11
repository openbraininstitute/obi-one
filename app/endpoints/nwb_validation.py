import asyncio
import pathlib
import tempfile
from http import HTTPStatus
from typing import Annotated, NoReturn

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.errors import (
    ApiErrorCode,
)
from app.logger import L


def _handle_empty_file(file: UploadFile) -> NoReturn:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.BAD_REQUEST,
            "detail": "Uploaded file is empty",
        },
    )


def _raise_validation_error(file: UploadFile, stderr: str, stdout: str,
                             returncode: int) -> NoReturn:
    """Raises an HTTPException for NWB validation failure."""
    error_output = stderr or stdout
    L.error(f"Nwb validation failed for file {file.filename}")
    L.error(f"Exit code {returncode}): {error_output}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.BAD_REQUEST,
            "detail": f"NWB validation failed: {error_output}",
        },
    )


async def _process_nwb(file: UploadFile, temp_file_path: str) -> None:
    """Validate nwb file with pynwb using asyncio subprocess."""
    command_args = ["pynwb-validate", temp_file_path]

    try:
        process = await asyncio.create_subprocess_exec(
            command_args[0],
            *command_args[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_data, stderr_data = await process.communicate()

        stdout = stdout_data.decode().strip()
        stderr = stderr_data.decode().strip()

        # Check the return code
        if process.returncode != 0:
            _raise_validation_error(file, stderr, stdout, process.returncode)

    except FileNotFoundError as e:
        L.error(f"Validation tool not found: {e!s}")
        # Catch exceptions if 'pynwb-validate' is not in the PATH
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": "Required validation tool 'pynwb-validate' not found.",
            },
        ) from e
    except Exception as e:
        L.error(f"Unexpected Nwb error validating file {file.filename}: {e!s}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"An unexpected error occurred during validation: {e!s}",
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
    ) -> None:
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

import asyncio
import pathlib
import tempfile
import zipfile
from http import HTTPStatus
from typing import Annotated

import morphio
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from morph_tool import convert

from app.dependencies.auth import user_verified
from app.errors import ApiErrorCode
from app.logger import L

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])


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


async def _process_and_convert_morphology(
    file: UploadFile, temp_file_path: str, file_extension: str
) -> tuple[str, str]:
    """Process and convert a neuron morphology file."""
    try:
        morphio.set_raise_warnings(False)
        _ = morphio.Morphology(temp_file_path)

        outputfile1, outputfile2 = "", ""
        if file_extension == ".swc":
            outputfile1 = temp_file_path.replace(".swc", "_converted.h5")
            outputfile2 = temp_file_path.replace(".swc", "_converted.asc")
        elif file_extension == ".h5":
            outputfile1 = temp_file_path.replace(".h5", "_converted.swc")
            outputfile2 = temp_file_path.replace(".h5", "_converted.asc")
        else:  # .asc
            outputfile1 = temp_file_path.replace(".asc", "_converted.swc")
            outputfile2 = temp_file_path.replace(".asc", "_converted.h5")

        convert(temp_file_path, outputfile1)
        convert(temp_file_path, outputfile2)

    except Exception as e:
        L.error(f"Morphio error loading file {file.filename}: {e!s}")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"Failed to load and convert the file: {e!s}",
            },
        ) from e
    else:
        return outputfile1, outputfile2


def _create_zip_file_sync(zip_path: str, file1: str, file2: str) -> None:
    """Synchronously create a zip file from two files."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as my_zip:
        my_zip.write(file1, arcname=f"{pathlib.Path(file1).name}")
        my_zip.write(file2, arcname=f"{pathlib.Path(file2).name}")


async def _create_and_return_zip(outputfile1: str, outputfile2: str) -> FileResponse:
    """Asynchronously creates a zip file and returns it as a FileResponse."""
    zip_filename = "morph_archive.zip"
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            _create_zip_file_sync,
            zip_filename,
            outputfile1,
            outputfile2,
        )
    except Exception as e:
        L.error(f"Error creating zip file: {e!s}")
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.BAD_REQUEST,
                "detail": f"Error creating zip file: {e!s}",
            },
        ) from e
    else:
        L.info(f"Created zip file: {zip_filename}")
        return FileResponse(path=zip_filename, filename=zip_filename, media_type="application/zip")


async def _validate_and_read_file(file: UploadFile) -> tuple[bytes, str]:
    """Validates file extension and reads content."""
    L.info(f"Received file upload: {file.filename}")
    allowed_extensions = {".swc", ".h5", ".asc"}
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


@router.post(
    "/test-neuron-file",
    summary="Validate morphology format and returns the conversion to other formats.",
    description="Tests a neuron file (.swc, .h5, or .asc) with basic validation.",
)
async def test_neuron_file(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
) -> FileResponse:
    content, file_extension = await _validate_and_read_file(file)

    temp_file_path = ""
    outputfile1, outputfile2 = "", ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        outputfile1, outputfile2 = await _process_and_convert_morphology(
            file=file, temp_file_path=temp_file_path, file_extension=file_extension
        )

        return await _create_and_return_zip(outputfile1, outputfile2)

    finally:
        if temp_file_path:
            try:
                pathlib.Path(temp_file_path).unlink(missing_ok=True)
                pathlib.Path(outputfile1).unlink(missing_ok=True)
                pathlib.Path(outputfile2).unlink(missing_ok=True)
            except OSError as e:
                L.error(f"Error deleting temporary files: {e!s}")

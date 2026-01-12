import asyncio
import pathlib
import tempfile
import zipfile
from http import HTTPStatus
from typing import Annotated

import morphio
import neurom
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from morph_tool import convert
from neurom.exceptions import NeuroMError

from app.dependencies.auth import user_verified
from app.errors import ApiErrorCode
from app.logger import L

router = APIRouter(prefix="/declared", tags=["declared"], dependencies=[Depends(user_verified)])

DEFAULT_SINGLE_POINT_SOMA_BY_EXT: dict[str, bool] = {
    ".h5": False,
    ".swc": True,
    ".asc": False,
}


def _handle_empty_file(file: UploadFile) -> None:
    """Handle empty file upload by raising an appropriate HTTPException."""
    L.error(f"Empty file uploaded: {file.filename}")
    raise HTTPException(
        status_code=HTTPStatus.BAD_REQUEST,
        detail={
            "code": ApiErrorCode.INVALID_REQUEST,
            "detail": "Uploaded file is empty",
        },
    )


async def process_and_convert_morphology(
    temp_file_path: str,
    file_extension: str,
    *,
    output_basename: str | None = None,
    single_point_soma_by_ext: dict[str, bool] | None = None,
) -> tuple[str, str]:
    """Process and convert a neuron morphology file."""
    try:
        morphio.set_raise_warnings(False)
        _ = morphio.Morphology(temp_file_path)

        temp_path = pathlib.Path(temp_file_path)
        out_dir = temp_path.parent
        stem = output_basename or temp_path.stem

        if file_extension == ".swc":
            target_exts = (".h5", ".asc")
        elif file_extension == ".h5":
            target_exts = (".swc", ".asc")
        else:  # ".asc"
            target_exts = (".swc", ".h5")

        outputfile1 = out_dir / f"{stem}{target_exts[0]}"
        outputfile2 = out_dir / f"{stem}{target_exts[1]}"

        mapping = single_point_soma_by_ext or DEFAULT_SINGLE_POINT_SOMA_BY_EXT

        convert(
            temp_file_path,
            str(outputfile1),
            single_point_soma=mapping.get(target_exts[0], False),
        )
        convert(
            temp_file_path,
            str(outputfile2),
            single_point_soma=mapping.get(target_exts[1], False),
        )

    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Failed to load and convert the file: {e!s}",
            },
        ) from e
    else:
        return str(outputfile1), str(outputfile2)


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
                "code": ApiErrorCode.INVALID_REQUEST,
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
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Invalid file extension. Must be one of {valid_extensions}",
            },
        )

    content = await file.read()
    if not content:
        _handle_empty_file(file)

    return content, file_extension


def _validate_soma_diameter(file_path: str, threshold: float = 100.0) -> bool:
    """Returns True if the soma radius is within the threshold.
    Returns False if it exceeds the threshold.
    """
    try:
        m = neurom.load_morphology(file_path)
        radius = m.soma.radius
    except (NeuroMError, OSError, AttributeError) as e:
        L.error(f"Error validating soma diameter for {file_path}: {e!s}")
        return False
    else:
        return radius <= threshold


@router.post(
    "/test-neuron-file",
    summary="Validate morphology format and returns the conversion to other formats.",
    description="Tests a neuron file (.swc, .h5, or .asc) with basic validation.",
)
async def test_neuron_file(
    file: Annotated[UploadFile, File(description="Neuron file to upload (.swc, .h5, or .asc)")],
    single_point_soma: Annotated[bool, Query(description="Convert soma to single point")] = False,  # noqa: PT028, FBT002
) -> FileResponse:
    content, file_extension = await _validate_and_read_file(file)

    temp_file_path = ""
    outputfile1, outputfile2 = "", ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        if not _validate_soma_diameter(temp_file_path):
            L.error(f"Unrealistic soma diameter detected in {file.filename}")
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail={
                    "code": ApiErrorCode.INVALID_REQUEST,
                    "detail": "Unrealistic soma diameter detected.",
                },
            )

        if single_point_soma:
            single_point_soma_by_ext = dict.fromkeys(DEFAULT_SINGLE_POINT_SOMA_BY_EXT, True)
        else:
            single_point_soma_by_ext = DEFAULT_SINGLE_POINT_SOMA_BY_EXT

        outputfile1, outputfile2 = await process_and_convert_morphology(
            temp_file_path=temp_file_path,
            file_extension=file_extension,
            single_point_soma_by_ext=single_point_soma_by_ext,
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

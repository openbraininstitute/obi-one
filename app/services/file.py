import shutil
import zipfile
from collections.abc import Iterable
from http import HTTPStatus
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.errors import ApiErrorCode

MAX_FILE_SIZE = 128 * 1024 * 1024  # bytes


def _validate_file_extension(
    filename: str | None, *, allowed_extensions: set[str], force_lower_case: bool
) -> str:
    """Validate the file name and extension."""
    if not filename:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "No filename provided",
            },
        )

    file_extension = Path(filename).suffix
    if force_lower_case:
        file_extension = file_extension.lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Invalid file extension. Must be one of {', '.join(allowed_extensions)}",
            },
        )
    return file_extension


def _validate_file_size(size: float | None, max_file_size: float) -> None:
    if not size or size <= 0:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": "File size is 0 or could not be determined.",
            },
        )
    if size > max_file_size:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"File size exceeds the maximum size of {max_file_size / (1024**2)} MB",
            },
        )


def save_upload_file(
    upload_file: UploadFile,
    output_dir: Path,
    *,
    output_stem: str,
    allowed_extensions: set[str],
    force_lower_case: bool,
) -> Path:
    """Validate the upload file and save it to the given directory.

    Args:
        upload_file: file uploaded by the user.
        output_dir: directory where to save the file.
        output_stem: stem of the output file (without extension).
        allowed_extensions: set of allowed file extensions (e.g. {".swc", ".h5", ".asc"}).
        force_lower_case: whether to convert the file extension to lower case before validating it.
    """
    _validate_file_size(
        size=upload_file.size,
        max_file_size=MAX_FILE_SIZE,
    )
    file_extension = _validate_file_extension(
        filename=upload_file.filename,
        allowed_extensions=allowed_extensions,
        force_lower_case=force_lower_case,
    )
    output_file = output_dir / f"{output_stem}{file_extension}"

    with output_file.open("wb") as f:
        shutil.copyfileobj(upload_file.file, f)

    return output_file


def create_zip_file(input_files: Iterable[Path], output_file: Path, *, delete_input: bool) -> None:
    """Create a zip file from the given input files, optionally deleting them once consumed.

    Args:
        input_files: iterable of files to include in the zip file.
        output_file: path of the output zip file.
        delete_input: whether to delete the input files after adding them to the zip file.
    """
    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for input_file in input_files:
            zip_file.write(input_file, arcname=input_file.name)
            if delete_input:
                input_file.unlink()

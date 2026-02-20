import logging
from collections.abc import Iterable
from http import HTTPStatus
from pathlib import Path

import morph_tool
import morphio
import neurom
from fastapi import HTTPException
from morphio import RawDataError
from neurom.exceptions import NeuroMError

from app.errors import ApiErrorCode

DEFAULT_SINGLE_POINT_SOMA_BY_EXT: dict[str, bool] = {
    ".h5": False,
    ".swc": True,
    ".asc": False,
}
ALLOWED_EXTENSIONS = set(DEFAULT_SINGLE_POINT_SOMA_BY_EXT)
SOMA_RADIUS_THRESHOLD = 100.0

L = logging.getLogger(__name__)


def validate_soma_diameter(file_path: Path, threshold: float = SOMA_RADIUS_THRESHOLD) -> bool:
    """Validate the soma diameter of the given morphology."""
    try:
        m = neurom.load_morphology(file_path)
        radius = m.soma.radius
        return radius is not None and 0 < float(radius) <= threshold
    except (NeuroMError, RawDataError, OSError, AttributeError) as e:
        L.warning(f"Error validating soma diameter for {file_path}: {e!s}")
        return False


def convert_morphology(
    input_file: Path,
    *,
    output_dir: Path,
    single_point_soma_by_ext: dict[str, bool],
    target_exts: Iterable[str] | None = None,
    output_stem: str | None = None,
) -> list[Path]:
    """Convert a morphology to other formats.

    Args:
        input_file: input morphology.
        output_dir: directory where to save the generated morphologies.
        single_point_soma_by_ext: map the extensions to single_point_soma (bool).
        target_exts: iterable of formats to generate, given as extensions (e.g. [".h5", ".asc"]).
            If None, generate all the formats different from the original.
        output_stem: stem of the output files. If None, use the same as the input file.
    """
    try:
        morphio.set_raise_warnings(False)
        morphio.Morphology(input_file)

        file_extension = input_file.suffix
        output_stem = output_stem or input_file.stem
        target_exts = target_exts or ALLOWED_EXTENSIONS - {file_extension}
        output_files = []
        for ext in target_exts:
            output_file = output_dir / f"{output_stem}{ext}"
            single_point_soma = single_point_soma_by_ext.get(ext, False)
            morph_tool.convert(
                input_file=str(input_file),
                output_file=str(output_file),
                single_point_soma=single_point_soma,
            )
            output_files.append(output_file)

    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Failed to load and convert the file: {e!s}",
            },
        ) from e
    return output_files

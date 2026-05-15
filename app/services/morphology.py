import logging
from collections.abc import Iterable
from http import HTTPStatus
from pathlib import Path
from typing import Any, Final

import morph_tool
import morphio
import neurom
from fastapi import HTTPException
from neurom.check.runner import CheckRunner
from neurom.exceptions import NeuroMError
from pydantic import BaseModel

from app.errors import ApiErrorCode

DEFAULT_SINGLE_POINT_SOMA_BY_EXT: dict[str, bool] = {
    ".h5": False,
    ".swc": True,
    ".asc": False,
}
ALLOWED_EXTENSIONS = set(DEFAULT_SINGLE_POINT_SOMA_BY_EXT)
SOMA_RADIUS_THRESHOLD = 100.0

L = logging.getLogger(__name__)

_QUALITY_CHECK_CONFIG: Final[dict] = {
    "checks": {
        "morphology_checks": [
            "has_axon",
            "has_basal_dendrite",
            "has_apical_dendrite",
            "has_no_jumps",
            "has_no_fat_ends",
            "has_nonzero_soma_radius",
            "has_all_nonzero_neurite_radii",
            "has_all_nonzero_section_lengths",
            "has_all_nonzero_segment_lengths",
            "has_no_flat_neurites",
            "has_no_narrow_start",
            "has_no_dangling_branch",
        ]
    },
    "options": {
        "has_nonzero_soma_radius": 0.0,
        "has_all_nonzero_neurite_radii": 0.007,
        "has_all_nonzero_segment_lengths": 0.01,
        "has_all_nonzero_section_lengths": 0.01,
    },
}

_quality_check_runner = CheckRunner(_QUALITY_CHECK_CONFIG)


class MorphologyFiles(BaseModel):
    swc: Path | None = None
    hdf5: Path | None = None
    asc: Path | None = None  # ADD THIS

    def paths(self) -> list[Path]:
        return [p for p in (self.swc, self.hdf5, self.asc) if p is not None]  # add self.asc


def run_quality_checks(file_path: Path) -> dict[str, Any]:
    """Run standard morphology quality checks and return a structured result.

    Returns a dict with:
      - "ran_to_completion": bool
      - "failed_checks": list[str]  – names of checks that returned False
      - "passed_checks": list[str]  – names of checks that returned True
    """
    try:
        neuron = neurom.load_morphology(file_path)
        _, check_results = _quality_check_runner._check_loop(neuron, "morphology_checks")
        return {
            "ran_to_completion": True,
            "failed_checks": [name for name, ok in check_results.items() if not ok],
            "passed_checks": [name for name, ok in check_results.items() if ok],
        }
    except Exception as exc:  # noqa: BLE001
        L.warning(f"run_quality_checks: could not complete checks for {file_path}: {exc}")
        return {
            "ran_to_completion": False,
            "failed_checks": [],
            "passed_checks": [],
        }


def _check_warnings(warning_handler: morphio.WarningHandlerCollector) -> None:
    warnings = warning_handler.get_all()
    if warnings:
        msg = "; ".join(str(w.warning) for w in warnings)
        raise morphio.MorphioError(msg)


def load_morphio_morphology(file_path: Path, *, raise_warnings: bool) -> morphio.Morphology:
    warning_handler = morphio.WarningHandlerCollector()
    try:
        morphology = morphio.Morphology(file_path, warning_handler=warning_handler)
        if raise_warnings:
            _check_warnings(warning_handler=warning_handler)
    except morphio.MorphioError as e:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Morphology validation failed: {e!s}",
            },
        ) from e
    return morphology


def _check_soma_radius(radius: float | None, threshold: float) -> None:
    if radius is None or not (0 < float(radius) <= threshold):
        msg = "Unrealistic soma diameter detected."
        raise ValueError(msg)


def validate_soma_diameter(file_path: Path, threshold: float = SOMA_RADIUS_THRESHOLD) -> None:
    try:
        m = neurom.load_morphology(file_path)
        _check_soma_radius(m.soma.radius, threshold)
    except (NeuroMError, ValueError) as e:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Soma diameter validation failed: {e!s}",
            },
        ) from e


def convert_morphology(
    input_file: Path,
    *,
    output_dir: Path,
    single_point_soma_by_ext: dict[str, bool],
    target_exts: Iterable[str] | None = None,
    output_stem: str | None = None,
) -> MorphologyFiles:
    try:
        file_extension = input_file.suffix
        output_stem = output_stem or input_file.stem
        target_exts = target_exts or ALLOWED_EXTENSIONS - {file_extension}

        output_paths = {}
        for ext in target_exts:
            output_file = output_dir / f"{output_stem}{ext}"
            single_point_soma = single_point_soma_by_ext.get(ext, False)
            morph_tool.convert(
                input_file=str(input_file),
                output_file=str(output_file),
                single_point_soma=single_point_soma,
            )
            if ext == ".swc":
                output_paths["swc"] = output_file
            elif ext == ".h5":
                output_paths["hdf5"] = output_file
            elif ext == ".asc":
                output_paths["asc"] = output_file

    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail={
                "code": ApiErrorCode.INVALID_REQUEST,
                "detail": f"Failed to convert the file: {e!s}",
            },
        ) from e
    return MorphologyFiles(**output_paths)


def validate_and_convert_morphology(
    input_file: Path,
    *,
    output_dir: Path,
    single_point_soma_by_ext: dict[str, bool],
    target_exts: Iterable[str] | None = None,
    output_stem: str | None = None,
) -> MorphologyFiles:
    load_morphio_morphology(input_file, raise_warnings=False)
    return convert_morphology(
        input_file,
        output_dir=output_dir,
        single_point_soma_by_ext=single_point_soma_by_ext,
        target_exts=target_exts,
        output_stem=output_stem,
    )

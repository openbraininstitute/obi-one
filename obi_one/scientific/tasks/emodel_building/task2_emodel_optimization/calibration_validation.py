"""MEModel calibration and bluecellulab validation helpers for Task 2.

Both computations run in spawned subprocesses because they instantiate a
``bluecellulab.Cell``: NEURON state accumulated by the optimisation run
(globals such as ``celsius``/``v_init``, already-defined hoc templates) must not
leak into the calibration/validation cell, and NEURON mechanism loading is
irreversible.

bluecellulab resolves the compiled mechanism library lazily at first ``Cell``
creation from ``<cwd>/<arch>`` (``x86_64``/``arm64``, auto-loaded by NEURON) or
``BLUECELLULAB_MOD_LIBRARY_PATH``. The workers therefore ``os.chdir(coord_root)``
*before* importing bluecellulab, where ``emodel_building_utils.compile_mechanisms``
has already produced the arch directory.

Keep top-level imports light: spawned children re-import this module, so it must
not import bluepyemodel, bluecellulab, or ``task.py`` at module level.
"""

import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from multiprocessing import get_context
from pathlib import Path

from entitysdk.types import ValidationStatus

L = logging.getLogger(__name__)

DEFAULT_CELSIUS = 34.0
DEFAULT_V_INIT = -80.0
# bluecellulab's run_validations defaults to 7 nested processes; keep that as the cap.
VALIDATION_MAX_PROCESSES = 7


def json_default(obj: object) -> object:
    """JSON fallback converting numpy scalars/arrays, Paths etc. to serialisable values."""
    tolist = getattr(obj, "tolist", None)
    if callable(tolist):
        return tolist()
    return str(obj)


def validation_status_from_results(validation_dict: dict) -> ValidationStatus:
    """Map a bluecellulab validation result dict to a MEModel ``ValidationStatus``.

    ``done`` only when at least one test ran and every test passed; otherwise the
    status stays ``created``. (A crash in calibration/validation is reported as
    ``error`` by the caller.)
    """
    tests = [
        value for value in validation_dict.values() if isinstance(value, dict) and "passed" in value
    ]
    if tests and all(bool(value["passed"]) for value in tests):
        return ValidationStatus.done
    return ValidationStatus.created


def compute_calibration_and_validation(
    coord_root: Path,
    hoc_path: Path,
    morphology_path: Path,
    *,
    cell_name: str,
    holding_current: float,
    threshold_current: float,
    output_dir: Path,
) -> dict:
    """Compute MEModel calibration, then run bluecellulab validation on it.

    Pure compute (subprocesses + local files only — no database calls). Raises
    on failure; the caller decides how to handle it.

    Returns:
        Dict with keys ``calibration`` and ``validation``.
    """
    calibration_dict = compute_calibration_in_subprocess(
        coord_root,
        hoc_path,
        morphology_path,
        holding_current=holding_current,
        threshold_current=threshold_current,
    )
    validation_dict = run_validations_in_subprocess(
        coord_root,
        hoc_path,
        morphology_path,
        cell_name,
        holding_current=calibration_dict["holding_current"],
        threshold_current=calibration_dict["rheobase"],
        output_dir=output_dir,
    )
    return {"calibration": calibration_dict, "validation": validation_dict}


def calibration_worker(
    coord_root: str,
    hoc_path: str,
    morphology_path: str,
    holding_current: float,
    threshold_current: float,
    result_json_path: str,
) -> None:
    """Compute MEModel calibration properties; runs in a spawned subprocess.

    Builds a ``bluecellulab.Cell`` and calls
    ``bluecellulab.tools.compute_memodel_properties``, writing
    ``{holding_current, rheobase, rin}`` to ``result_json_path`` for the parent.
    """
    os.chdir(coord_root)
    from bluecellulab import Cell  # ruff: ignore[import-outside-top-level]
    from bluecellulab.circuit.circuit_access import (  # ruff: ignore[import-outside-top-level]
        EmodelProperties,
    )
    from bluecellulab.tools import (  # ruff: ignore[import-outside-top-level]
        compute_memodel_properties,
    )

    emodel_properties = EmodelProperties(
        threshold_current=threshold_current,
        holding_current=holding_current,
        AIS_scaler=1.0,
    )
    cell = Cell(
        template_path=hoc_path,
        morphology_path=morphology_path,
        template_format="v6",
        emodel_properties=emodel_properties,
    )

    calibration_dict = compute_memodel_properties(cell)
    Path(result_json_path).write_text(
        json.dumps(calibration_dict, indent=2, default=json_default), encoding="utf-8"
    )


def validation_worker(
    coord_root: str,
    hoc_path: str,
    morphology_path: str,
    cell_name: str,
    holding_current: float,
    threshold_current: float,
    celsius: float,
    v_init: float,
    n_processes: int,
    output_dir: str,
    result_json_path: str,
) -> None:
    """Run bluecellulab validations; runs in a spawned subprocess.

    ``run_validations`` internally uses a ``NestedPool`` of worker processes, so
    this process must stay non-daemonic. Results are written to
    ``result_json_path`` for the parent.
    """
    os.chdir(coord_root)
    from bluecellulab import Cell  # ruff: ignore[import-outside-top-level]
    from bluecellulab.circuit.circuit_access import (  # ruff: ignore[import-outside-top-level]
        EmodelProperties,
    )
    from bluecellulab.validation.validation import (  # ruff: ignore[import-outside-top-level]
        run_validations,
    )

    emodel_properties = EmodelProperties(
        threshold_current=threshold_current,
        holding_current=holding_current,
        AIS_scaler=1.0,
    )
    cell = Cell(
        template_path=hoc_path,
        morphology_path=morphology_path,
        template_format="v6",
        emodel_properties=emodel_properties,
    )

    validation_dict = run_validations(
        cell,
        cell_name,
        output_dir=output_dir,
        celsius=celsius,
        v_init=v_init,
        n_processes=n_processes,
    )

    Path(result_json_path).write_text(
        json.dumps(validation_dict, indent=2, default=json_default), encoding="utf-8"
    )


def run_worker_in_subprocess(target: Callable[..., object], args: tuple, description: str) -> dict:
    """Run ``target`` in a spawned subprocess and return its JSON result file.

    The last element of ``args`` must be the path the worker writes its result
    JSON to. Raises ``RuntimeError`` on non-zero exit or missing output.
    """
    fd, result_json_path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    Path(result_json_path).unlink()  # let the worker create it

    process = get_context("spawn").Process(target=target, args=(*args, result_json_path))
    process.start()
    process.join()

    if process.exitcode != 0:
        msg = (
            f"{description} subprocess failed with exit code {process.exitcode}. "
            "Check logs for bluecellulab/NEURON errors."
        )
        raise RuntimeError(msg)

    result_path = Path(result_json_path)
    if not result_path.exists():
        msg = f"{description} subprocess did not produce a result file."
        raise RuntimeError(msg)

    result = json.loads(result_path.read_text(encoding="utf-8"))
    result_path.unlink()
    return result


def compute_calibration_in_subprocess(
    coord_root: Path,
    hoc_path: Path,
    morphology_path: Path,
    *,
    holding_current: float = 0.0,
    threshold_current: float = 0.0,
) -> dict:
    """Compute ``holding_current``/``rheobase``/``rin`` in an isolated subprocess.

    Returns:
        Dict with keys ``holding_current``, ``rheobase``, ``rin``.
    """
    L.info("Computing MEModel calibration in subprocess")
    result = run_worker_in_subprocess(
        calibration_worker,
        (
            str(coord_root),
            str(hoc_path),
            str(morphology_path),
            holding_current,
            threshold_current,
        ),
        "Calibration",
    )
    L.info(
        "Calibration computed: holding=%s, rheobase=%s, rin=%s",
        result.get("holding_current"),
        result.get("rheobase"),
        result.get("rin"),
    )
    return result


def run_validations_in_subprocess(
    coord_root: Path,
    hoc_path: Path,
    morphology_path: Path,
    cell_name: str,
    *,
    holding_current: float = 0.0,
    threshold_current: float = 0.0,
    celsius: float = DEFAULT_CELSIUS,
    v_init: float = DEFAULT_V_INIT,
    n_processes: int | None = None,
    output_dir: Path,
) -> dict:
    """Run bluecellulab validations in an isolated subprocess.

    Returns:
        Dict from ``run_validations`` with per-test results and figure paths.
    """
    if n_processes is None:
        n_processes = min(VALIDATION_MAX_PROCESSES, os.cpu_count() or 1)

    L.info("Running validations in subprocess for %s", cell_name)
    return run_worker_in_subprocess(
        validation_worker,
        (
            str(coord_root),
            str(hoc_path),
            str(morphology_path),
            cell_name,
            holding_current,
            threshold_current,
            celsius,
            v_init,
            n_processes,
            str(output_dir),
        ),
        "Validation",
    )


def locate_hoc(coord_root: Path, seed: int) -> Path:
    """Locate the exported HOC and verify compiled mechanisms exist.

    The HOC comes from the SONATA export (``export_emodels_sonata``). With
    ``only_best=False`` several candidates may exist; prefer a filename
    containing ``seed=<seed>``. The morphology and mechanisms are pipeline
    inputs — the caller passes the morphology path in, and this function only
    verifies the compiled arch dir (``arm64``/``x86_64``) exists.
    """
    sonata_dir = coord_root / "export_emodels_sonata"
    hoc_candidates = sorted(sonata_dir.rglob("*.hoc")) if sonata_dir.exists() else []
    if not hoc_candidates:
        msg = f"No .hoc file found under {sonata_dir}; SONATA export missing."
        raise FileNotFoundError(msg)
    if len(hoc_candidates) > 1:
        seeded = [p for p in hoc_candidates if re.search(rf"seed={seed}(?!\d)", p.stem)]
        if len(seeded) == 1:
            hoc_candidates = seeded
        else:
            msg = (
                f"Ambiguous HOC candidates under {sonata_dir}: "
                f"{[p.name for p in hoc_candidates]} (seed={seed})."
            )
            raise RuntimeError(msg)
    hoc_path = hoc_candidates[0]

    for arch in ("x86_64", "arm64"):
        if (coord_root / arch / "special").exists():
            break
    else:
        msg = (
            f"No compiled mechanisms (arm64|x86_64/special) under {coord_root}; "
            "run compile_mechanisms first."
        )
        raise FileNotFoundError(msg)

    L.info("Calibration/validation HOC: %s", hoc_path)
    return hoc_path

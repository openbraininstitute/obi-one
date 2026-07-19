"""Shared helpers for the four emodel-optimisation pipeline stages.

These helpers materialise a BluePyEModel working directory inside a stage's
``coordinate_output_root`` so that BluePyEModel can be invoked with relative
paths (its access points read ``./config/recipes.json``, write to
``./checkpoints/``, ``./figures/<emodel>/``, ``./final.json`` etc.).
"""

import json
import logging
import os
import shutil
import subprocess  # noqa: S404
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

L = logging.getLogger(__name__)

# BluePyEModel working-directory subpaths that downstream stages must see.
WORKING_DIR_SUBPATHS: tuple[str, ...] = (
    "config",
    "morphologies",
    "mechanisms",
    "ephys_data",
    "extraction",
    "extracted_features.json",
    "checkpoints",
    "figures",
    "recordings",
    "run",
    "x86_64",
    "arm64",
    "final.json",
    "export_emodels_hoc",
    "export_emodels_sonata",
)


@contextmanager
def chdir(path: Path) -> Iterator[None]:
    """Temporarily change the working directory to ``path``."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def copy_tree(source: Path, target: Path) -> None:
    """Copy ``source`` (file or directory) to ``target``, creating parents."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True)
    else:
        shutil.copy2(source, target)


def seed_working_dir_from_previous(
    previous_stage_output_path: Path,
    coordinate_output_root: Path,
) -> None:
    """Copy every BluePyEModel working-directory artefact from a previous stage.

    Only the well-known subpaths in :data:`WORKING_DIR_SUBPATHS` are copied so
    that we don't drag along OBI-ONE bookkeeping files
    (``obi_one_scan.json``, ``obi_one_coordinate.json``).
    """
    if not previous_stage_output_path.exists():
        msg = f"previous_stage_output_path does not exist: {previous_stage_output_path}"
        raise FileNotFoundError(msg)

    for sub in WORKING_DIR_SUBPATHS:
        source = previous_stage_output_path / sub
        if source.exists():
            target = coordinate_output_root / sub
            copy_tree(source, target)
            L.info("Seeded %s -> %s", source, target)


def load_recipes(recipes_path: Path) -> dict:
    """Read a ``recipes.json`` file and return the parsed dict."""
    with recipes_path.open(encoding="utf-8") as f:
        return json.load(f)


def write_recipes(recipes: dict, recipes_path: Path) -> None:
    """Write a ``recipes.json`` file with the standard BluePyEModel layout."""
    recipes_path.parent.mkdir(parents=True, exist_ok=True)
    with recipes_path.open("w", encoding="utf-8") as f:
        json.dump(recipes, f, indent=4)


def update_pipeline_settings(
    recipes: dict,
    emodel: str,
    overrides: dict[str, Any],
) -> dict:
    """Merge ``overrides`` into ``recipes[emodel]['pipeline_settings']``.

    ``None`` values in ``overrides`` are skipped so callers can pass partial
    blocks without clobbering existing recipe settings.
    """
    if emodel not in recipes:
        msg = f"emodel '{emodel}' not in recipes (got keys: {list(recipes)})"
        raise KeyError(msg)

    settings = recipes[emodel].setdefault("pipeline_settings", {})
    for key, value in overrides.items():
        if value is None:
            continue
        settings[key] = value
    return recipes


def _resolve_nrnivmodl() -> str:
    """Return an absolute path to ``nrnivmodl``.

    Falls back to ``<sys.prefix>/bin/nrnivmodl`` so the task still works inside
    a venv whose ``bin/`` directory hasn't been prepended to ``PATH`` (e.g. when
    Jupyter is launched without first activating the venv).
    """
    found = shutil.which("nrnivmodl")
    if found:
        return found
    candidate = Path(sys.prefix) / "bin" / "nrnivmodl"
    if candidate.exists():
        return str(candidate)
    msg = (
        "Could not locate nrnivmodl. Install NEURON in the active venv"
        " (BluePyEModel pulls it in as a dependency) or add nrnivmodl to PATH."
    )
    raise FileNotFoundError(msg)


def compile_mechanisms(mechanisms_dir: Path) -> None:
    """Compile NEURON mod files via ``nrnivmodl``.

    Looks for already-compiled output (`x86_64/special` or `arm64/special` next
    to ``mechanisms_dir``) and skips compilation if found.
    """
    if not mechanisms_dir.is_dir():
        msg = f"mechanisms_dir is not a directory: {mechanisms_dir}"
        raise FileNotFoundError(msg)

    parent = mechanisms_dir.parent
    for arch in ("x86_64", "arm64"):
        if (parent / arch / "special").exists():
            L.info("Mechanisms already compiled (%s); skipping nrnivmodl.", arch)
            return

    nrnivmodl = _resolve_nrnivmodl()
    L.info("Compiling NEURON mechanisms in %s with %s ...", mechanisms_dir, nrnivmodl)
    subprocess.run(  # noqa: S603
        [nrnivmodl, mechanisms_dir.name],
        cwd=parent,
        check=True,
    )


def run_plot_models(
    access_point: Any,
    mapper: object,
    seeds: list[int],
    figures_dir: Path,
    *,
    only_validated: bool = False,
) -> None:
    """Run ``plotting.plot_models`` with all settings from the access point.

    Centralises the ~20 keyword arguments that ``plotting.plot_models`` expects,
    reading them from ``access_point.pipeline_settings``. Only
    ``only_validated`` differs between task2 (False) and task3 (True/user-set).
    """
    from bluepyemodel.emodel_pipeline import plotting  # noqa: PLC0415

    pp = access_point.pipeline_settings
    plotting.plot_models(
        access_point=access_point,
        mapper=mapper,
        seeds=seeds,
        figures_dir=figures_dir,
        plot_optimisation_progress=pp.plot_optimisation_progress,
        optimiser=pp.optimiser,
        plot_parameter_evolution=pp.plot_parameter_evolution,
        plot_distributions=pp.plot_distributions,
        plot_scores=pp.plot_scores,
        plot_traces=pp.plot_traces,
        plot_thumbnail=pp.plot_thumbnail,
        plot_currentscape=pp.plot_currentscape,
        plot_dendritic_ISI_CV=pp.plot_dendritic_ISI_CV,
        plot_dendritic_rheobase=pp.plot_dendritic_rheobase,
        plot_bAP_EPSP=pp.plot_bAP_EPSP,
        plot_IV_curve=pp.plot_IV_curves,
        plot_FI_curve_comparison=pp.plot_FI_curve_comparison,
        plot_phase_plot=pp.plot_phase_plot,
        plot_traces_comparison=pp.plot_traces_comparison,
        run_plot_custom_sinspec=pp.run_plot_custom_sinspec,
        IV_curve_prot_name=pp.IV_curve_prot_name,
        FI_curve_prot_name=pp.FI_curve_prot_name,
        phase_plot_settings=pp.phase_plot_settings,
        sinespec_settings=pp.sinespec_settings,
        custom_bluepyefe_cells_pklpath=pp.custom_bluepyefe_cells_pklpath,
        custom_bluepyefe_protocols_pklpath=pp.custom_bluepyefe_protocols_pklpath,
        only_validated=only_validated,
        save_recordings=pp.save_recordings,
    )


def determine_core_count(
    offspring_size: int,
    max_ngen: int,
    *,
    max_cpus: int | None = None,
) -> int:
    """Deterministically compute the number of CPU cores for an optimisation run.

    The formula is::

        cores = min(offspring_size, max_cpus if given else offspring_size)

    Rationale:
        - Each individual in a generation is evaluated independently, so
          ``offspring_size`` is the natural upper bound for parallelism.
        - Capping at ``max_cpus`` (default: ``os.cpu_count()``) avoids
          oversubscription when the job is allocated fewer cores than the
          offspring size.
        - ``max_ngen`` does not affect core count (generations run
          sequentially), but is accepted as a parameter for future extensions
          (e.g. adaptive resource allocation).

    The result is always at least 1.
    """
    if offspring_size < 1:
        msg = f"offspring_size must be >= 1, got {offspring_size}"
        raise ValueError(msg)
    if max_ngen < 1:
        msg = f"max_ngen must be >= 1, got {max_ngen}"
        raise ValueError(msg)

    if max_cpus is None:
        max_cpus = os.cpu_count() or 1

    return max(1, min(offspring_size, max_cpus))

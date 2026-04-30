"""Task wrapper for the aind-ephys-postprocessing capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.config import (
    AINDEPhysPostprocessingSingleConfig,
)

L = logging.getLogger(__name__)

POSTPROCESSING_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-postprocessing.git"
POSTPROCESSING_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-postprocessing")  # noqa: S108


def _ensure_postprocessing_repo(repo_path: Path = POSTPROCESSING_REPO_DEFAULT_PATH) -> Path:
    """Clone the postprocessing capsule on first use; reuse the existing clone afterwards.

    Patches the cloned ``run_capsule.py`` for spikeinterface API drift (the
    ``qm_params`` kwarg of ``SortingAnalyzer.compute('quality_metrics', ...)``
    was renamed to ``metric_params``).
    """
    if not repo_path.exists():
        L.info("Cloning %s -> %s", POSTPROCESSING_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", POSTPROCESSING_REPO_URL, str(repo_path)],
            check=True,
        )
    capsule_py = repo_path / "code" / "run_capsule.py"
    if capsule_py.is_file():
        src = capsule_py.read_text()
        patched = src.replace(
            "qm_params=quality_metrics_params", "metric_params=quality_metrics_params"
        )
        if patched != src:
            capsule_py.write_text(patched)
            L.info("Patched run_capsule.py: qm_params -> metric_params")
    return repo_path


def _seed_data_dir(
    data_dir: Path, preprocessing_source: Path, spikesort_source: Path
) -> tuple[int, int]:
    """Seed the capsule's ``data/`` from preprocessing + spike-sorting outputs.

    Returns ``(num_preprocessed, num_spikesorted)``.
    """
    n_pre = 0
    for entry in preprocessing_source.iterdir():
        if (
            entry.is_dir()
            and entry.name.startswith("preprocessed_")
            and not entry.name.endswith(".json")
        ):
            shutil.copytree(entry, data_dir / entry.name)
            n_pre += 1
        elif entry.is_file() and entry.suffix == ".json" and (
            entry.name.startswith("binary_") or entry.name.startswith("preprocessed_")
        ):
            shutil.copy2(entry, data_dir / entry.name)

    n_sort = 0
    for entry in spikesort_source.iterdir():
        if entry.is_dir() and entry.name.startswith("spikesorted_"):
            shutil.copytree(entry, data_dir / entry.name)
            n_sort += 1
    return n_pre, n_sort


class AINDEPhysPostprocessingTask(Task):
    """Run the aind-ephys-postprocessing capsule on preprocessed + sorted ephys data.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-postprocessing``
         and patched for spikeinterface API drift.
      2. Seed its ``data/`` folder with ``preprocessed_<name>/`` +
         ``binary_<name>.json`` from ``initialize.preprocessing_output_path``
         and ``spikesorted_<name>/`` from ``initialize.spikesort_output_path``.
      3. Serialise this config to a ``params_obi.json`` next to the script.
      4. Invoke ``python -u code/run_capsule.py --params params_obi.json
         --n-jobs <n> [--use-motion-corrected]`` from the capsule's ``code/``.
      5. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys Postprocessing"
    description: ClassVar[str] = "Run the aind-ephys-postprocessing capsule."

    config: AINDEPhysPostprocessingSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_postprocessing_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        pre_source = Path(self.config.initialize.preprocessing_output_path)
        sort_source = Path(self.config.initialize.spikesort_output_path)
        if not pre_source.exists():
            msg = f"preprocessing_output_path does not exist: {pre_source}"
            raise FileNotFoundError(msg)
        if not sort_source.exists():
            msg = f"spikesort_output_path does not exist: {sort_source}"
            raise FileNotFoundError(msg)

        n_pre, n_sort = _seed_data_dir(data_dir, pre_source, sort_source)
        if n_pre == 0:
            msg = f"No preprocessed_<name>/ directories found in {pre_source}"
            raise FileNotFoundError(msg)
        if n_sort == 0:
            msg = f"No spikesorted_<name>/ directories found in {sort_source}"
            raise FileNotFoundError(msg)
        L.info(
            "Seeded %d preprocessed + %d spikesorted recording(s) into %s",
            n_pre,
            n_sort,
            data_dir,
        )

        params_path = code_dir / "params_obi.json"
        params_path.write_text(json.dumps(self.config.params_dict(), indent=2))

        argv: list[str] = [
            "python",
            "-u",
            "run_capsule.py",
            "--params",
            params_path.name,
            "--n-jobs",
            str(self.config.initialize.n_jobs),
        ]
        if self.config.initialize.use_motion_corrected:
            argv.append("--use-motion-corrected")

        L.info("Running %s", " ".join(argv))
        result = subprocess.run(  # noqa: S603
            argv,
            cwd=code_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        L.info(result.stdout)
        if result.returncode != 0:
            L.error(result.stderr)
            msg = f"aind-ephys-postprocessing failed with code {result.returncode}"
            raise RuntimeError(msg)

        target = Path(self.config.coordinate_output_root)
        target.mkdir(parents=True, exist_ok=True)
        for entry in results_dir.iterdir():
            dest = target / entry.name
            if dest.exists():
                shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
            if entry.is_dir():
                shutil.copytree(entry, dest)
            else:
                shutil.copy2(entry, dest)

        return target

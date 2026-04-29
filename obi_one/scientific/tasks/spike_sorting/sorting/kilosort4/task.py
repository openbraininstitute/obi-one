"""Task wrapper for the aind-ephys-spikesort-kilosort4 capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.spike_sorting.sorting.kilosort4.config import (
    AINDEPhysSpikesortKilosort4SingleConfig,
)

L = logging.getLogger(__name__)

KS4_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-spikesort-kilosort4.git"
KS4_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-spikesort-kilosort4")  # noqa: S108


def _ensure_ks4_repo(repo_path: Path = KS4_REPO_DEFAULT_PATH) -> Path:
    """Clone the Kilosort4 capsule on first use; reuse the existing clone afterwards."""
    if not repo_path.exists():
        L.info("Cloning %s -> %s", KS4_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", KS4_REPO_URL, str(repo_path)],
            check=True,
        )
    return repo_path


def _seed_data_dir(data_dir: Path, source: Path) -> int:
    """Seed the capsule's ``data/`` with ``preprocessed_*`` dirs and ``binary_*.json``.

    Returns the number of preprocessed recordings copied.
    """
    n = 0
    for entry in source.iterdir():
        if entry.is_dir() and entry.name.startswith("preprocessed_") and not entry.name.endswith(
            ".json"
        ):
            shutil.copytree(entry, data_dir / entry.name)
            n += 1
        elif entry.is_file() and entry.name.startswith("binary_") and entry.suffix == ".json":
            shutil.copy2(entry, data_dir / entry.name)
        elif entry.is_file() and entry.name.startswith("preprocessed_") and entry.suffix == ".json":
            shutil.copy2(entry, data_dir / entry.name)
    return n


class AINDEPhysSpikesortKilosort4Task(Task):
    """Run the aind-ephys-spikesort-kilosort4 capsule on preprocessed ephys recordings.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-spikesort-kilosort4``.
      2. Seed its ``data/`` folder with every ``preprocessed_<name>/`` directory
         and matching ``binary_<name>.json`` from
         ``initialize.preprocessing_output_path``.
      3. Serialise this config to a ``params_obi.json`` next to the script.
      4. Invoke ``python -u code/run_capsule.py --params params_obi.json``
         (plus ``--skip-motion-correction`` / ``--clear-cache`` /
         ``--min-drift-channels`` / ``--n-jobs`` flags) from the capsule's
         ``code/`` cwd.
      5. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys Spikesort Kilosort4"
    description: ClassVar[str] = "Run the aind-ephys-spikesort-kilosort4 capsule."

    config: AINDEPhysSpikesortKilosort4SingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_ks4_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        source = Path(self.config.initialize.preprocessing_output_path)
        if not source.exists():
            msg = f"preprocessing_output_path does not exist: {source}"
            raise FileNotFoundError(msg)
        n_recordings = _seed_data_dir(data_dir, source)
        if n_recordings == 0:
            msg = f"No preprocessed_<name>/ directories found in {source}"
            raise FileNotFoundError(msg)
        L.info("Seeded %d preprocessed recording(s) into %s", n_recordings, data_dir)

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
            "--min-drift-channels",
            str(self.config.initialize.min_drift_channels),
        ]
        if self.config.initialize.skip_motion_correction:
            argv.append("--skip-motion-correction")
        if self.config.initialize.clear_cache:
            argv.append("--clear-cache")
        if self.config.initialize.raise_if_fails:
            argv.append("--raise-if-fails")

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
            msg = f"aind-ephys-spikesort-kilosort4 failed with code {result.returncode}"
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

"""Task wrapper for the aind-ephys-preprocessing capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingSingleConfig,
)

L = logging.getLogger(__name__)

PREPROCESSING_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-preprocessing.git"
PREPROCESSING_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-preprocessing")  # noqa: S108


def _ensure_preprocessing_repo(repo_path: Path = PREPROCESSING_REPO_DEFAULT_PATH) -> Path:
    """Clone the preprocessing capsule on first use; reuse the existing clone afterwards."""
    if not repo_path.exists():
        L.info("Cloning %s -> %s", PREPROCESSING_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", PREPROCESSING_REPO_URL, str(repo_path)],
            check=True,
        )
    return repo_path


class AINDEPhysPreprocessingTask(Task):
    """Run the aind-ephys-preprocessing capsule on dispatched ephys jobs.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-preprocessing``.
      2. Seed its ``data/`` folder with every ``job_*.json`` from
         ``initialize.dispatch_output_path``.
      3. Serialise this config to a ``params_obi.json`` next to the script.
      4. Invoke ``python -u code/run_capsule.py --params params_obi.json
         --motion <skip|compute|apply> --t-start <s> --t-stop <s> --n-jobs <n>``
         from the capsule's ``code/`` cwd.
      5. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys Preprocessing"
    description: ClassVar[str] = "Run the aind-ephys-preprocessing capsule."

    config: AINDEPhysPreprocessingSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_preprocessing_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        # Clean previous-run inputs/outputs.
        for stale in data_dir.glob("job_*.json"):
            stale.unlink()
        for stale in list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        dispatch_output_path = Path(self.config.initialize.dispatch_output_path)
        if not dispatch_output_path.exists():
            msg = f"dispatch_output_path does not exist: {dispatch_output_path}"
            raise FileNotFoundError(msg)
        job_files = sorted(dispatch_output_path.glob("job_*.json"))
        if not job_files:
            msg = f"No job_*.json files found in {dispatch_output_path}"
            raise FileNotFoundError(msg)
        for jf in job_files:
            shutil.copy2(jf, data_dir / jf.name)
        L.info("Seeded %d job file(s) into %s", len(job_files), data_dir)

        # Write the capsule params.json from the config.
        params_path = code_dir / "params_obi.json"
        params_path.write_text(json.dumps(self.config.params_dict(), indent=2))

        motion_arg = "skip"
        if self.config.motion_correction.compute:
            motion_arg = "apply" if self.config.motion_correction.apply else "compute"

        argv: list[str] = [
            "python",
            "-u",
            "run_capsule.py",
            "--params",
            params_path.name,
            "--motion",
            motion_arg,
            "--n-jobs",
            str(self.config.initialize.n_jobs),
        ]
        if self.config.initialize.t_start is not None:
            argv += ["--t-start", str(self.config.initialize.t_start)]
        if self.config.initialize.t_stop is not None:
            argv += ["--t-stop", str(self.config.initialize.t_stop)]

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
            msg = f"aind-ephys-preprocessing failed with code {result.returncode}"
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

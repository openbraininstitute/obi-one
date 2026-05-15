"""Task wrapper for the aind-ephys-qc-collector capsule."""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._09_qc_collector.config import (
    AINDEPhysQCCollectorSingleConfig,
)

L = logging.getLogger(__name__)

QCC_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-qc-collector.git"
QCC_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-qc-collector")  # noqa: S108


def _ensure_qcc_repo(repo_path: Path = QCC_REPO_DEFAULT_PATH) -> Path:
    if not repo_path.exists():
        L.info("Cloning %s -> %s", QCC_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", QCC_REPO_URL, str(repo_path)],
            check=True,
        )
    return repo_path


class AINDEPhysQCCollectorTask(Task):
    """Run the aind-ephys-qc-collector capsule.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-qc-collector``.
      2. Seed its ``data/`` folder with the contents of
         ``initialize.qc_output_path`` (per-recording ``quality_control_*.json``
         + ``quality_control_<name>/`` figure folders).
      3. Invoke ``python -u code/run_capsule.py`` from the capsule's ``code/``.
      4. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys QC Collector"
    description: ClassVar[str] = "Run the aind-ephys-qc-collector capsule."

    config: AINDEPhysQCCollectorSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_qcc_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        source = Path(self.config.initialize.qc_output_path)
        if not source.exists():
            msg = f"qc_output_path does not exist: {source}"
            raise FileNotFoundError(msg)
        n = 0
        for entry in source.iterdir():
            if entry.is_dir() and entry.name.startswith("quality_control_"):
                shutil.copytree(entry, data_dir / entry.name)
                n += 1
            elif (
                entry.is_file()
                and entry.name.startswith("quality_control_")
                and entry.suffix == ".json"
            ):
                shutil.copy2(entry, data_dir / entry.name)
        if n == 0:
            msg = f"No quality_control_<name>/ folders found in {source}"
            raise FileNotFoundError(msg)
        L.info("Seeded %d QC recording(s) into %s", n, data_dir)

        argv: list[str] = ["python", "-u", "run_capsule.py"]
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
            msg = f"aind-ephys-qc-collector failed with code {result.returncode}"
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

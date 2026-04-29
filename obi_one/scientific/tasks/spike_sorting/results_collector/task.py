"""Task wrapper for the aind-ephys-results-collector capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.spike_sorting.results_collector.config import (
    AINDEPhysResultsCollectorSingleConfig,
)

L = logging.getLogger(__name__)

RC_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-results-collector.git"
RC_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-results-collector")  # noqa: S108


def _ensure_rc_repo(repo_path: Path = RC_REPO_DEFAULT_PATH) -> Path:
    if not repo_path.exists():
        L.info("Cloning %s -> %s", RC_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", RC_REPO_URL, str(repo_path)],
            check=True,
        )
    return repo_path


class AINDEPhysResultsCollectorTask(Task):
    """Run the aind-ephys-results-collector capsule.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-results-collector``.
      2. Seed its ``data/`` folder with the union of every previous-stage
         output directory plus a synthetic ``ecephys_<session>/`` folder
         containing ``subject.json`` + ``data_description.json`` (the capsule
         hard-asserts exactly one ``ecephys_*`` folder is present).
      3. Invoke ``python -u code/run_capsule.py --process-name <name>`` from
         the capsule's ``code/`` cwd.
      4. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys Results Collector"
    description: ClassVar[str] = "Run the aind-ephys-results-collector capsule."

    config: AINDEPhysResultsCollectorSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_rc_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        sources = [
            Path(self.config.initialize.dispatch_output_path),
            Path(self.config.initialize.preprocessing_output_path),
            Path(self.config.initialize.spikesort_output_path),
            Path(self.config.initialize.postprocessing_output_path),
            Path(self.config.initialize.curation_output_path),
            Path(self.config.initialize.visualization_output_path),
        ]
        for source in sources:
            if not source.exists():
                msg = f"Input path does not exist: {source}"
                raise FileNotFoundError(msg)
            for entry in source.iterdir():
                dest = data_dir / entry.name
                if dest.exists():
                    continue
                if entry.is_dir():
                    shutil.copytree(entry, dest)
                else:
                    shutil.copy2(entry, dest)

        # Synthesize the ecephys session folder the capsule asserts on.
        session_folder = data_dir / self.config.initialize.session_name
        if not session_folder.name.startswith("ecephys"):
            msg = (
                f"session_name must start with 'ecephys' (got"
                f" {self.config.initialize.session_name!r})"
            )
            raise ValueError(msg)
        session_folder.mkdir(exist_ok=True)
        (session_folder / "subject.json").write_text(
            json.dumps({"subject_id": self.config.initialize.subject_id})
        )
        (session_folder / "data_description.json").write_text(
            json.dumps(self.config.synthetic_data_description(), indent=2)
        )
        L.info("Seeded data dir: %s", data_dir)

        argv: list[str] = [
            "python",
            "-u",
            "run_capsule.py",
            "--process-name",
            self.config.initialize.process_name,
        ]
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
            msg = f"aind-ephys-results-collector failed with code {result.returncode}"
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

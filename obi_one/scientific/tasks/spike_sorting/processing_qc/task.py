"""Task wrapper for the aind-ephys-processing-qc capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.spike_sorting.processing_qc.config import (
    AINDEPhysProcessingQCSingleConfig,
)

L = logging.getLogger(__name__)

QC_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-processing-qc.git"
QC_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-processing-qc")  # noqa: S108


def _ensure_qc_repo(repo_path: Path = QC_REPO_DEFAULT_PATH) -> Path:
    """Clone the processing-QC capsule and patch ``qc_utils.py`` for spikeinterface API drift.

    Newer spikeinterface (a) requires ``ignore_low_freq_error=True`` for
    ``bandpass_filter`` cutoffs below ~0.5 Hz, and (b) renamed
    ``template_metrics['half_width']`` to ``'trough_half_width'``.
    """
    if not repo_path.exists():
        L.info("Cloning %s -> %s", QC_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", QC_REPO_URL, str(repo_path)],
            check=True,
        )
    qc_utils = repo_path / "code" / "qc_utils.py"
    if qc_utils.is_file():
        src = qc_utils.read_text()
        patched = src.replace(
            "spre.bandpass_filter(recording, freq_min=0.1, freq_max=freq_lfp)",
            "spre.bandpass_filter(recording, freq_min=0.1, freq_max=freq_lfp,"
            " ignore_low_freq_error=True)",
        ).replace("template_metrics['half_width']", "template_metrics['trough_half_width']")
        if patched != src:
            qc_utils.write_text(patched)
            L.info("Patched qc_utils.py")
    return repo_path


class AINDEPhysProcessingQCTask(Task):
    """Run the aind-ephys-processing-qc capsule.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-processing-qc``
         and patched for spikeinterface API drift.
      2. Seed its ``data/`` folder with the contents of
         ``initialize.collected_output_path`` (the results-collector layout)
         plus the dispatch ``job_*.json`` and a synthetic ``ecephys_*``
         session folder (the capsule expects exactly one).
      3. Invoke ``python -u code/run_capsule.py [--no-event-metrics]
         --min-duration-allow-failed <s>`` from the capsule's ``code/`` cwd.
      4. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys Processing QC"
    description: ClassVar[str] = "Run the aind-ephys-processing-qc capsule."

    config: AINDEPhysProcessingQCSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_qc_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        collected = Path(self.config.initialize.collected_output_path)
        dispatch_source = Path(self.config.initialize.dispatch_output_path)
        if not collected.exists():
            msg = f"collected_output_path does not exist: {collected}"
            raise FileNotFoundError(msg)
        if not dispatch_source.exists():
            msg = f"dispatch_output_path does not exist: {dispatch_source}"
            raise FileNotFoundError(msg)

        for entry in collected.iterdir():
            dest = data_dir / entry.name
            if entry.is_dir():
                shutil.copytree(entry, dest)
            else:
                shutil.copy2(entry, dest)
        for entry in dispatch_source.iterdir():
            if entry.is_file() and entry.name.startswith("job_"):
                dest = data_dir / entry.name
                if not dest.exists():
                    shutil.copy2(entry, dest)

        session_name = self.config.initialize.session_name
        if not session_name.startswith("ecephys"):
            msg = f"session_name must start with 'ecephys' (got {session_name!r})"
            raise ValueError(msg)
        session_folder = data_dir / session_name
        session_folder.mkdir(exist_ok=True)
        (session_folder / "subject.json").write_text(
            json.dumps({"subject_id": self.config.initialize.subject_id})
        )
        L.info("Seeded data dir: %s", data_dir)

        argv: list[str] = [
            "python",
            "-u",
            "run_capsule.py",
            "--min-duration-allow-failed",
            str(self.config.initialize.min_duration_allow_failed),
        ]
        if not self.config.initialize.compute_event_metrics:
            argv.append("--no-event-metrics")

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
            msg = f"aind-ephys-processing-qc failed with code {result.returncode}"
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

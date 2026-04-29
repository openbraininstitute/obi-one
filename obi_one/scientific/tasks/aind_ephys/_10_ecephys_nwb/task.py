"""Task wrapper for the aind-ecephys-nwb capsule."""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._10_ecephys_nwb.config import (
    AINDEcephysNWBSingleConfig,
)

L = logging.getLogger(__name__)

NWB_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ecephys-nwb.git"
NWB_REPO_DEFAULT_PATH = Path("/tmp/aind-ecephys-nwb")  # noqa: S108


def _ensure_nwb_repo(repo_path: Path = NWB_REPO_DEFAULT_PATH) -> Path:
    """Clone the NWB-export capsule and patch ``run_capsule.py`` for neuroconv API drift."""
    if not repo_path.exists():
        L.info("Cloning %s -> %s", NWB_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", NWB_REPO_URL, str(repo_path)],
            check=True,
        )
    capsule_py = repo_path / "code" / "run_capsule.py"
    if capsule_py.is_file():
        src = capsule_py.read_text()
        patched = src.replace(
            "add_electrodes_info_to_nwbfile", "add_electrodes_to_nwbfile"
        )
        if patched != src:
            capsule_py.write_text(patched)
            L.info("Patched run_capsule.py: add_electrodes_info_to_nwbfile -> add_electrodes_to_nwbfile")
    return repo_path


class AINDEcephysNWBTask(Task):
    """Run the aind-ecephys-nwb capsule.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ecephys-nwb`` and patched
         for neuroconv API drift.
      2. Seed its ``data/`` folder with the dispatch ``job_*.json``.
      3. Invoke ``python -u code/run_capsule.py --backend <backend>
         [--write-raw] [--skip-lfp] [--stub --stub-seconds <s>]
         --lfp_temporal_factor <n> --lfp_spatial_factor <n>
         --lfp_highpass_freq_min <hz>`` from the capsule's ``code/``.
      4. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ecephys NWB Export"
    description: ClassVar[str] = "Run the aind-ecephys-nwb capsule."

    config: AINDEcephysNWBSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_nwb_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        source = Path(self.config.initialize.dispatch_output_path)
        if not source.exists():
            msg = f"dispatch_output_path does not exist: {source}"
            raise FileNotFoundError(msg)
        n = 0
        for entry in source.iterdir():
            if entry.is_file() and entry.name.startswith("job_") and entry.suffix == ".json":
                shutil.copy2(entry, data_dir / entry.name)
                n += 1
        if n == 0:
            msg = f"No job_*.json files found in {source}"
            raise FileNotFoundError(msg)
        L.info("Seeded %d job file(s) into %s", n, data_dir)

        argv: list[str] = [
            "python",
            "-u",
            "run_capsule.py",
            "--backend",
            self.config.initialize.backend,
            "--lfp_temporal_factor",
            str(self.config.lfp.temporal_factor),
            "--lfp_spatial_factor",
            str(self.config.lfp.spatial_factor),
            "--lfp_highpass_freq_min",
            str(self.config.lfp.highpass_freq_min),
        ]
        if self.config.initialize.write_raw:
            argv.append("--write-raw")
        if self.config.initialize.skip_lfp:
            argv.append("--skip-lfp")
        if self.config.initialize.stub:
            argv += ["--stub", "--stub-seconds", str(self.config.initialize.stub_seconds)]

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
            msg = f"aind-ecephys-nwb failed with code {result.returncode}"
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

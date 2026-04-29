"""Task wrapper for the aind-ephys-curation capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._05_curation.config import (
    AINDEPhysCurationSingleConfig,
)

L = logging.getLogger(__name__)

CURATION_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-curation.git"
CURATION_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-curation")  # noqa: S108


def _ensure_curation_repo(repo_path: Path = CURATION_REPO_DEFAULT_PATH) -> Path:
    """Clone the curation capsule on first use; reuse the existing clone afterwards."""
    if not repo_path.exists():
        L.info("Cloning %s -> %s", CURATION_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", CURATION_REPO_URL, str(repo_path)],
            check=True,
        )
    return repo_path


def _seed_data_dir(data_dir: Path, source: Path) -> int:
    """Seed the capsule's ``data/`` with ``postprocessed_<name>.zarr`` folders.

    Returns the number of zarr folders copied.
    """
    n = 0
    for entry in source.iterdir():
        if (
            entry.is_dir()
            and entry.name.startswith("postprocessed_")
            and entry.suffix == ".zarr"
        ):
            shutil.copytree(entry, data_dir / entry.name)
            n += 1
    return n


class AINDEPhysCurationTask(Task):
    """Run the aind-ephys-curation capsule on postprocessed ephys analyzers.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-curation``.
      2. Seed its ``data/`` folder with every ``postprocessed_<name>.zarr``
         folder from ``initialize.postprocessing_output_path``.
      3. Serialise this config to a ``params_obi.json`` next to the script.
      4. Invoke ``python -u code/run_capsule.py --params params_obi.json
         --n-jobs <n>`` from the capsule's ``code/`` cwd.
      5. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys Curation"
    description: ClassVar[str] = "Run the aind-ephys-curation capsule."

    config: AINDEPhysCurationSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_curation_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        source = Path(self.config.initialize.postprocessing_output_path)
        if not source.exists():
            msg = f"postprocessing_output_path does not exist: {source}"
            raise FileNotFoundError(msg)
        n = _seed_data_dir(data_dir, source)
        if n == 0:
            msg = f"No postprocessed_<name>.zarr folders found in {source}"
            raise FileNotFoundError(msg)
        L.info("Seeded %d postprocessed analyzer(s) into %s", n, data_dir)

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
            msg = f"aind-ephys-curation failed with code {result.returncode}"
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

"""Task wrapper for the aind-ephys-visualization capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._06_visualization.config import (
    AINDEPhysVisualizationSingleConfig,
)

L = logging.getLogger(__name__)

VIZ_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-visualization.git"
VIZ_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-visualization")  # noqa: S108


def _ensure_viz_repo(repo_path: Path = VIZ_REPO_DEFAULT_PATH) -> Path:
    """Clone the visualization capsule on first use; reuse the existing clone afterwards."""
    if not repo_path.exists():
        L.info("Cloning %s -> %s", VIZ_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", VIZ_REPO_URL, str(repo_path)],
            check=True,
        )
    return repo_path


def _seed_data_dir(data_dir: Path, sources: list[Path]) -> None:
    """Flat-merge the contents of every ``source`` directory into ``data_dir``.

    Skips ``data_process_*.json`` provenance files (not consumed by the
    visualization capsule).
    """
    for source in sources:
        for entry in source.iterdir():
            if entry.name.startswith("data_process_"):
                continue
            if entry.name == "obi_one_coordinate.json":
                continue
            dest = data_dir / entry.name
            if dest.exists():
                continue
            if entry.is_dir():
                shutil.copytree(entry, dest)
            else:
                shutil.copy2(entry, dest)


class AINDEPhysVisualizationTask(Task):
    """Run the aind-ephys-visualization capsule on the ephys-pipeline outputs.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-ephys-visualization``.
      2. Seed its ``data/`` folder with the union of dispatch +
         preprocessing + postprocessing + curation outputs.
      3. Serialise this config to a ``params_obi.json`` next to the script.
      4. Invoke ``python -u code/run_capsule.py --params params_obi.json
         --output-format <fmt> --n-jobs <n>`` from the capsule's ``code/``.
      5. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Ephys Visualization"
    description: ClassVar[str] = "Run the aind-ephys-visualization capsule."

    config: AINDEPhysVisualizationSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_viz_repo()
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
            Path(self.config.initialize.postprocessing_output_path),
            Path(self.config.initialize.curation_output_path),
        ]
        for source in sources:
            if not source.exists():
                msg = f"Input path does not exist: {source}"
                raise FileNotFoundError(msg)
        _seed_data_dir(data_dir, sources)
        L.info("Seeded data dir: %s", data_dir)

        params_path = code_dir / "params_obi.json"
        params_path.write_text(json.dumps(self.config.params_dict(), indent=2))

        argv: list[str] = [
            "python",
            "-u",
            "run_capsule.py",
            "--params",
            params_path.name,
            "--output-format",
            self.config.initialize.output_format,
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
            msg = f"aind-ephys-visualization failed with code {result.returncode}"
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

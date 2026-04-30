import logging
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._01_dispatch.config import AINDEPhysDispatchSingleConfig

L = logging.getLogger(__name__)

DISPATCH_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-ephys-job-dispatch.git"
DISPATCH_REPO_DEFAULT_PATH = Path("/tmp/aind-ephys-job-dispatch")  # noqa: S108


def _ensure_dispatch_repo(repo_path: Path = DISPATCH_REPO_DEFAULT_PATH) -> Path:
    """Clone the dispatch capsule on first use; reuse the existing clone afterwards."""
    if not repo_path.exists():
        L.info("Cloning %s -> %s", DISPATCH_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", DISPATCH_REPO_URL, str(repo_path)],
            check=True,
        )
    return repo_path


class AINDEPhysDispatchTask(Task):
    """Run the aind-ephys-job-dispatch capsule for a single dispatch configuration.

    The capsule's `code/run_capsule.py` parses the recording, applies the
    `--debug` / `--min-recording-duration` / `--spikeinterface-info` flags
    encoded by `AINDEPhysDispatchSingleConfig.command_line_representation()`,
    and writes one or more `job_*.json` files describing the recordings to
    process. Those JSON files are copied into this single config's
    ``coordinate_output_root`` so that downstream stages can locate them.
    """

    name: ClassVar[str] = "Multi Electrode Recording Postprocessing"
    description: ClassVar[str] = "Spike sorting preprocessing configuration."

    config: AINDEPhysDispatchSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        command = self.config.command_line_representation()
        L.info(command)

        repo = _ensure_dispatch_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in results_dir.glob("job_*.json"):
            stale.unlink()

        # The command is rooted at `code/run_capsule.py`; cd into `code/` and
        # strip the prefix so the script's relative `../data` / `../results`
        # paths resolve.
        argv = [a.removeprefix("code/") for a in shlex.split(command)]
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
            msg = f"aind-ephys-job-dispatch failed with code {result.returncode}"
            raise RuntimeError(msg)

        target = Path(self.config.coordinate_output_root)
        target.mkdir(parents=True, exist_ok=True)
        for jf in sorted(results_dir.glob("job_*.json")):
            shutil.copy2(jf, target / jf.name)

        return target

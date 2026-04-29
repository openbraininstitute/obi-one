"""Task wrapper for the aind-units-nwb capsule."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import entitysdk

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._11_units_nwb.config import (
    AINDUnitsNWBSingleConfig,
)

L = logging.getLogger(__name__)

UNITS_NWB_REPO_URL = "https://github.com/AllenNeuralDynamics/aind-units-nwb.git"
UNITS_NWB_REPO_DEFAULT_PATH = Path("/tmp/aind-units-nwb")  # noqa: S108


def _ensure_units_nwb_repo(repo_path: Path = UNITS_NWB_REPO_DEFAULT_PATH) -> Path:
    """Clone the units-NWB capsule and patch ``utils.py`` for neuroconv API drift."""
    if not repo_path.exists():
        L.info("Cloning %s -> %s", UNITS_NWB_REPO_URL, repo_path)
        subprocess.run(
            ["git", "clone", "--depth=1", UNITS_NWB_REPO_URL, str(repo_path)],
            check=True,
        )
    utils_py = repo_path / "code" / "utils.py"
    if utils_py.is_file():
        src = utils_py.read_text()
        patched = src.replace(
            "add_electrodes_info_to_nwbfile", "add_electrodes_to_nwbfile"
        ).replace("add_units_table_to_nwbfile", "_add_units_table_to_nwbfile")
        if patched != src:
            utils_py.write_text(patched)
            L.info("Patched utils.py for neuroconv API drift")
    return repo_path


class AINDUnitsNWBTask(Task):
    """Run the aind-units-nwb capsule.

    For each single config:
      1. Ensure the capsule is cloned to ``/tmp/aind-units-nwb`` and patched
         for neuroconv API drift.
      2. Seed its ``data/`` folder with the base NWB, the results-collector
         ``preprocessed/`` / ``curated/`` / ``spikesorted/`` / ``postprocessed/``
         directories, the dispatch ``job_*.json``, and a synthetic ``ecephys_*``
         session folder.
      3. Invoke ``python -u code/run_capsule.py [--stub --stub-units <n>]``
         from the capsule's ``code/`` cwd.
      4. Copy everything under ``../results/`` into ``coordinate_output_root``.
    """

    name: ClassVar[str] = "AIND Units NWB Export"
    description: ClassVar[str] = "Run the aind-units-nwb capsule."

    config: AINDUnitsNWBSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # noqa: ARG002
        entity_cache: bool = False,  # noqa: ARG002
        execution_activity_id: str | None = None,  # noqa: ARG002
    ) -> Path:
        repo = _ensure_units_nwb_repo()
        code_dir = repo / "code"
        data_dir = repo / "data"
        results_dir = repo / "results"
        data_dir.mkdir(exist_ok=True)
        results_dir.mkdir(exist_ok=True)

        for stale in list(data_dir.iterdir()) + list(results_dir.iterdir()):
            shutil.rmtree(stale) if stale.is_dir() else stale.unlink()

        nwb_input = Path(self.config.initialize.nwb_input_path)
        collected = Path(self.config.initialize.collected_output_path)
        dispatch_source = Path(self.config.initialize.dispatch_output_path)
        for p in (nwb_input, collected, dispatch_source):
            if not p.exists():
                msg = f"Input path does not exist: {p}"
                raise FileNotFoundError(msg)

        n_nwb = 0
        for entry in nwb_input.iterdir():
            if entry.is_file() and entry.suffix == ".nwb":
                shutil.copy2(entry, data_dir / entry.name)
                n_nwb += 1
            elif entry.is_dir() and entry.suffixes[-2:] == [".nwb", ".zarr"]:
                shutil.copytree(entry, data_dir / entry.name)
                n_nwb += 1
        if n_nwb == 0:
            msg = f"No .nwb / .nwb.zarr files found in {nwb_input}"
            raise FileNotFoundError(msg)

        for entry in collected.iterdir():
            if entry.name in {"preprocessed", "curated", "spikesorted", "postprocessed"}:
                shutil.copytree(entry, data_dir / entry.name)

        for entry in dispatch_source.iterdir():
            if entry.is_file() and entry.name.startswith("job_") and entry.suffix == ".json":
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

        argv: list[str] = ["python", "-u", "run_capsule.py"]
        if self.config.initialize.stub:
            argv += ["--stub", "--stub-units", str(self.config.initialize.stub_units)]

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
            msg = f"aind-units-nwb failed with code {result.returncode}"
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

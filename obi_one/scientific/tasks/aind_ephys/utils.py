"""SpikeInterface helpers shared by the AIND ephys pipeline stages.

Stages hand over through folders laid out as in the AIND pipeline: ``job_<i>.json`` from dispatch,
``preprocessed_<name>/`` and ``binary_<name>.json`` from preprocessing, ``spikesorted_<name>/``
from spike sorting and ``postprocessed_<name>.zarr`` from postprocessing. A stage that skips a
recording writes its output folder with only an ``error.txt`` inside, which later stages skip.
"""

import json
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import spikeinterface as si
from spikeinterface.core.core_tools import SIJsonEncoder

ERROR_FILE_NAME = "error.txt"
JOB_FILE_PREFIX = "job_"
# Analyzer extensions saved as pickles (fitted PCA models), which numcodecs refuses to decode.
PICKLED_EXTENSIONS = ("principal_components",)


@contextmanager
def global_job_kwargs(job_kwargs: dict) -> Generator[None]:
    """Use ``job_kwargs`` as spikeinterface's global job kwargs inside the block."""
    previous = si.get_global_job_kwargs()
    si.set_global_job_kwargs(**job_kwargs)
    try:
        yield
    finally:
        si.set_global_job_kwargs(**previous)


def write_jobs(jobs: list[dict], folder: Path) -> list[Path]:
    """Write one ``job_<i>.json`` per job into ``folder``."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, job in enumerate(jobs):
        path = folder / f"{JOB_FILE_PREFIX}{index}.json"
        path.write_text(json.dumps(job, indent=4, cls=SIJsonEncoder), encoding="utf-8")
        paths.append(path)
    return paths


def read_jobs(folder: Path) -> list[dict]:
    """The jobs the dispatch stage wrote into ``folder``, in index order."""
    paths = sorted(
        folder.glob(f"{JOB_FILE_PREFIX}*.json"),
        key=lambda path: int(path.stem.removeprefix(JOB_FILE_PREFIX)),
    )
    if not paths:
        msg = f"No {JOB_FILE_PREFIX}*.json files in {folder}; run the dispatch stage first."
        raise FileNotFoundError(msg)
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def dump_recording(
    recording: si.BaseRecording, folder: Path, stem: str, relative_to: Path | None
) -> Path:
    """Dump ``recording`` to ``<stem>.json``, or to ``<stem>.pkl`` if it is not JSON-able."""
    if recording.check_serializability("json"):
        path = folder / f"{stem}.json"
        recording.dump_to_json(path, relative_to=relative_to)
    else:
        path = folder / f"{stem}.pkl"
        recording.dump_to_pickle(path, relative_to=relative_to)
    return path


def load_recording(source: Path | dict, base_folder: Path | None = None) -> si.BaseRecording:
    """Load a recording from a file, folder or serialized dict."""
    recording = si.load(source, base_folder=base_folder)
    if not isinstance(recording, si.BaseRecording):
        msg = f"Expected a recording, loaded a {type(recording).__name__}."
        raise TypeError(msg)
    return recording


def load_sorting(folder: Path) -> si.BaseSorting:
    """Load a sorting saved into ``folder``."""
    sorting = si.load(folder)
    if not isinstance(sorting, si.BaseSorting):
        msg = f"Expected a sorting in {folder}, loaded a {type(sorting).__name__}."
        raise TypeError(msg)
    return sorting


def load_analyzer(folder: Path) -> si.SortingAnalyzer:
    """Load a sorting analyzer saved into ``folder``, without its pickled extensions."""
    analyzer = si.load_sorting_analyzer(folder, load_extensions=False)
    for name in analyzer.get_saved_extension_names():
        if name not in PICKLED_EXTENSIONS:
            analyzer.load_extension(name)
    return analyzer


def load_dumped_recording(folder: Path, stem: str) -> si.BaseRecording:
    """Load a recording written by :func:`dump_recording` with ``relative_to=folder``."""
    for suffix in (".json", ".pkl"):
        path = folder / f"{stem}{suffix}"
        if path.is_file():
            return load_recording(path, base_folder=folder)
    msg = f"Neither {stem}.json nor {stem}.pkl exists in {folder}."
    raise FileNotFoundError(msg)


def stage_output_names(folder: Path, prefix: str, suffix: str = "") -> list[str]:
    """Recording names of the ``<prefix><name><suffix>`` folders a stage wrote into ``folder``."""
    return sorted(
        path.name.removeprefix(prefix).removesuffix(suffix)
        for path in folder.iterdir()
        if path.is_dir() and path.name.startswith(prefix) and path.name.endswith(suffix)
    )


def remove_outputs(*paths: Path) -> None:
    """Remove what an earlier run of a stage wrote for a recording, so the stage can rerun."""
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def write_skip(folder: Path, reason: str) -> None:
    """Mark a recording as skipped by writing only ``error.txt`` into its output folder."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ERROR_FILE_NAME).write_text(reason, encoding="utf-8")


def was_skipped(folder: Path) -> bool:
    """Whether an earlier stage skipped the recording whose output is ``folder``."""
    return (folder / ERROR_FILE_NAME).is_file()


def write_data_process(
    path: Path,
    *,
    name: str,
    parameters: dict,
    outputs: dict,
    notes: str,
    start: datetime,
) -> None:
    """Record what a stage did to one recording, in place of AIND's ``DataProcess``."""
    record = {
        "name": name,
        "start_date_time": start.isoformat(),
        "end_date_time": datetime.now(UTC).isoformat(),
        "parameters": parameters,
        "outputs": outputs,
        "notes": notes,
    }
    path.write_text(json.dumps(record, indent=3, cls=SIJsonEncoder), encoding="utf-8")

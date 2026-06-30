"""On-the-fly materialization of Kilosort4 input.

When ``AINDEPhysSpikesortKilosort4SingleConfig.initialize.preprocessing_output_path``
is ``None`` the task has no preprocessed recordings to sort, so it generates them
from scratch: synthesise a toy ground-truth recording, then run the dispatch and
preprocessing stages on it, producing the same ``preprocessed_<name>/`` layout
the capsule seeds from.

``materialize_preprocessing_output`` is the single entry point; it delegates each
stage to a helper. Every stage runs in its own isolated environment (the toy
recording in a spikeinterface-only venv, dispatch and preprocessing in their
capsules' venvs), so obi-one's ``.venv`` is never touched.
"""

import logging
import subprocess  # noqa: S404
import tempfile
from pathlib import Path

from obi_one.scientific.tasks.aind_ephys._01_dispatch.blocks import (
    DispatchBasic,
    DispatchDataDependent,
    DispatchDebug,
    SpikeInterfaceInfo,
)
from obi_one.scientific.tasks.aind_ephys._01_dispatch.config import AINDEPhysDispatchSingleConfig
from obi_one.scientific.tasks.aind_ephys._01_dispatch.task import AINDEPhysDispatchTask
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import MotionCorrection
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.task import AINDEPhysPreprocessingTask
from obi_one.scientific.tasks.aind_ephys.capsule_runtime import ensure_capsule_python

L = logging.getLogger(__name__)

# Cached isolated env used only to synthesise the toy recording (needs spikeinterface).
_TOY_RECORDING_ENV_PATH = Path("/tmp/aind-ephys-ks4-toygen")  # noqa: S108
_TOY_RECORDING_ENV_DEPS = ["spikeinterface==0.104.7"]

# Mirrors examples/K_extracellular/00_generate_toy_recording.ipynb.
_TOY_RECORDING_GEN_SCRIPT = """\
import sys

import spikeinterface.full as si

out_dir = sys.argv[1]
recording, _ = si.generate_ground_truth_recording(
    durations=[10.0],
    sampling_frequency=30_000.0,
    num_channels=70,
    num_units=10,
    seed=2205,
)
recording.save(folder=out_dir, n_jobs=1, chunk_duration="1s", verbose=False)
"""


def materialize_preprocessing_output() -> Path:
    """Generate a toy recording and run dispatch + preprocessing on the fly.

    Used when ``preprocessing_output_path`` is ``None``: produces the same
    ``preprocessed_<name>/`` layout the Kilosort4 capsule seeds from, by chaining
    a synthesised toy recording through the dispatch and preprocessing stages.

    Returns:
        Directory holding the preprocessed recording(s), to seed the capsule from.
    """
    work = Path(tempfile.mkdtemp(prefix="aind-ephys-ks4-materialize-"))
    L.info("Materializing Kilosort4 input under %s", work)
    recording_dir = _generate_toy_recording(work / "recording")
    dispatch_dir = _run_dispatch(recording_dir, work / "dispatch")
    return _run_preprocessing(dispatch_dir, work / "preprocessing")


def _generate_toy_recording(out_dir: Path) -> Path:
    """Synthesise a toy ground-truth recording in an isolated spikeinterface env."""
    python = ensure_capsule_python(_TOY_RECORDING_ENV_PATH, _TOY_RECORDING_ENV_DEPS)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    script = out_dir.parent / "_generate_toy_recording.py"
    script.write_text(_TOY_RECORDING_GEN_SCRIPT, encoding="utf-8")
    L.info("Generating toy recording -> %s", out_dir)
    subprocess.run([python, str(script), str(out_dir)], check=True)  # noqa: S603
    return out_dir


def _run_dispatch(recording_dir: Path, out_dir: Path) -> Path:
    """Run the dispatch stage on ``recording_dir``; returns its output directory."""
    config = AINDEPhysDispatchSingleConfig(
        dispatch_basic=DispatchBasic(
            split_segments=True,
            split_groups=True,
            skip_timestamps_check=False,
            min_recording_duration=1.0,
        ),
        dispatch_data_dependent=DispatchDataDependent(
            input_format="spikeinterface",
            multi_session_data=False,
            spikeinterface_info=SpikeInterfaceInfo(
                reader_type="binaryfolder",
                reader_kwargs={"folder_path": str(recording_dir)},
            ),
        ),
        dispatch_debug=DispatchDebug(debug_mode=False, debug_duration=10.0),
    )
    config.coordinate_output_root = str(out_dir)
    AINDEPhysDispatchTask(config=config).execute()
    return out_dir


def _run_preprocessing(dispatch_dir: Path, out_dir: Path) -> Path:
    """Run the preprocessing stage on ``dispatch_dir``; returns its output directory."""
    config = AINDEPhysPreprocessingSingleConfig(
        initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
            dispatch_output_path=dispatch_dir,
            denoising_strategy="cmr",
            filter_type="highpass",
            min_preprocessing_duration=0.5,
            remove_out_channels=True,
            remove_bad_channels=True,
            max_bad_channel_fraction=0.5,
            t_start=0.0,
            t_stop=9.0,
            n_jobs=1,
        ),
        motion_correction=MotionCorrection(compute=False, apply=False),
    )
    config.coordinate_output_root = str(out_dir)
    AINDEPhysPreprocessingTask(config=config).execute()
    return out_dir

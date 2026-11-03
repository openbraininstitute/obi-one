"""Preprocessing stage: dispatch a raw recording into jobs, then filter and denoise each."""

import itertools
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import entitysdk
import numpy as np
import spikeinterface as si
import spikeinterface.preprocessing as spre
from spikeinterface.preprocessing.detect_bad_channels import DetectAndRemoveBadChannelsRecording
from spikeinterface.sortingcomponents.motion import interpolate_motion

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._01_dispatch.task import dispatch_jobs
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import MotionCorrection
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys.utils import (
    JOB_FILE_PREFIX,
    dump_recording,
    global_job_kwargs,
    load_recording,
    remove_outputs,
    write_data_process,
    write_jobs,
    write_skip,
)

if TYPE_CHECKING:
    from spikeinterface.core.base import BaseExtractor

L = logging.getLogger(__name__)


def clip(
    recording: si.BaseRecording, t_start: float | None, t_stop: float | None
) -> si.BaseRecording:
    """Clip a single-segment recording to [t_start, t_stop]; multi-segment ones are kept whole."""
    if t_start is None and t_stop is None:
        return recording
    if recording.get_num_segments() > 1:
        L.info("Not clipping a recording with %d segments.", recording.get_num_segments())
        return recording
    start = t_start or 0.0
    stop = min(t_stop if t_stop is not None else recording.get_duration(), recording.get_duration())
    fs = recording.get_sampling_frequency()
    return recording.frame_slice(start_frame=int(start * fs), end_frame=int(stop * fs + 1))


def apply_steps(
    recording: si.BaseRecording, steps: dict[str, dict]
) -> tuple[si.BaseRecording | None, str]:
    """Apply the steps, dropping the last one after each failure as the AIND pipeline does.

    Returns the preprocessed recording, None if every step failed, and notes on what was dropped.
    """
    steps = dict(steps)
    notes = ""
    while steps:
        try:
            return spre.apply_preprocessing_pipeline(recording, steps), notes
        except Exception as error:  # ruff: ignore[blind-except]
            last = next(reversed(steps))
            L.warning("Preprocessing failed (%s); retrying without %s.", error, last)
            notes += f"- Dropped {last} after: {error}\n"
            steps.pop(last)
    return None, notes


def bad_channel_labels(recording: si.BaseRecording) -> list[str] | None:
    """The labels the bad-channel step gave each channel, if the chain has that step."""
    step: BaseExtractor | None = recording
    while step is not None:
        if isinstance(step, DetectAndRemoveBadChannelsRecording):
            labels = step._kwargs.get("channel_labels")  # ruff: ignore[private-member-access]
            return None if labels is None else [str(label) for label in labels]
        step = step.get_parent()
    return None


def split_concatenated(recording: si.BaseRecording, segment_lengths: list[int]) -> si.BaseRecording:
    """Split a recording concatenated from segments of the given lengths back into segments."""
    offsets = np.concatenate([[0], np.cumsum(segment_lengths)])
    return si.append_recordings(
        [
            recording.frame_slice(start_frame=int(start), end_frame=int(end))
            for start, end in itertools.pairwise(offsets)
        ]
    )


def estimate_motion(
    binary: si.BaseRecording,
    processed: si.BaseRecording,
    motion_correction: MotionCorrection,
    folder: Path,
) -> tuple[si.BaseRecording | None, str]:
    """Estimate the probe's motion into ``folder``; return the corrected chain if it is applied."""
    segment_lengths = [binary.get_num_samples(i) for i in range(binary.get_num_segments())]
    concatenate = len(segment_lengths) > 1
    binary_c = si.concatenate_recordings([binary]) if concatenate else binary
    probe_span_um = float(np.ptp(binary.get_channel_locations()[:, 1]))
    L.info("Computing motion with preset %s.", motion_correction.preset)
    motion = spre.compute_motion(
        binary_c,
        preset=motion_correction.preset,
        folder=folder,
        detect_kwargs=motion_correction.detect_kwargs,
        select_kwargs=motion_correction.select_kwargs,
        localize_peaks_kwargs=motion_correction.localize_peaks_kwargs,
        estimate_motion_kwargs=motion_correction.estimate_motion_dict(probe_span_um),
        raise_error=False,
    )
    if motion is None:
        return None, "- Motion estimation failed; motion was not corrected.\n"
    if not motion_correction.apply:
        return None, ""

    processed_c = si.concatenate_recordings([processed]) if concatenate else processed
    corrected = interpolate_motion(
        processed_c.astype("float32"), motion=motion, **motion_correction.interpolate_motion_kwargs
    )
    if concatenate:
        corrected = split_concatenated(corrected, segment_lengths)
    return corrected, ""


class AINDEPhysPreprocessingTask(Task):
    """Dispatch the raw recording into jobs and preprocess each into this config's output folder.

    The NWB file is the local one given, or the recording entity's NWB asset, downloaded into
    ``input/`` (kept, since the lazy ``preprocessed_<name>.json`` chains point into it). The jobs
    are written as ``job_<i>.json``, so later stages can read this folder as the dispatch output.
    A recording that is too short, loses too many channels or fails every step gets a
    ``preprocessed_<name>/`` holding only ``error.txt``, which the later stages skip.
    """

    name: ClassVar[str] = "AIND Ephys Preprocessing"
    description: ClassVar[str] = "Preprocesses a raw extracellular recording."

    config: AINDEPhysPreprocessingSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> Path:
        output_folder = Path(self.config.coordinate_output_root)
        output_folder.mkdir(parents=True, exist_ok=True)
        nwb_path = self.stage_nwb(output_folder, db_client)
        jobs = dispatch_jobs(nwb_path, self.config.dispatch)
        for stale in output_folder.glob(f"{JOB_FILE_PREFIX}*.json"):
            stale.unlink()
        write_jobs(jobs, output_folder)
        L.info("Dispatched %s into %d jobs.", nwb_path.name, len(jobs))
        with global_job_kwargs(self.config.job_kwargs.to_dict()):
            for job in jobs:
                self.preprocess(job, output_folder)
        return output_folder

    def stage_nwb(self, output_folder: Path, db_client: entitysdk.client.Client | None) -> Path:
        """The local NWB file, or the recording entity's NWB asset downloaded into ``input/``."""
        init = self.config.initialize
        if init.nwb_path is not None:
            return Path(init.nwb_path)
        if init.recording is None or db_client is None:
            msg = "A recording and a db_client are needed to download the recording's NWB asset."
            raise ValueError(msg)
        return init.recording.download_nwb_asset(
            dest_dir=output_folder / "input", db_client=db_client
        )

    def preprocess(self, job: dict, output_folder: Path) -> None:
        """Preprocess one dispatched recording."""
        start = datetime.now(UTC)
        init = self.config.initialize
        name = job["recording_name"]
        recording = load_recording(job["recording_dict"], base_folder=Path(job["input_folder"]))
        if job.get("skip_times"):
            recording.reset_times()
        if recording.get_dtype().kind == "u":
            recording = spre.unsigned_to_signed(recording)
        recording = clip(recording, init.t_start, init.t_stop)
        L.info("Preprocessing %s: %.2f s.", name, recording.get_total_duration())

        recording_folder = output_folder / f"preprocessed_{name}"
        remove_outputs(
            recording_folder,
            output_folder / f"motion_{name}",
            *(
                output_folder / f"{stem}_{name}{suffix}"
                for stem in ("binary", "preprocessed", "motioncorrected")
                for suffix in (".json", ".pkl")
            ),
        )
        steps = self.config.preprocessing_pipeline(
            has_inter_sample_shift="inter_sample_shift" in recording.get_property_keys()
        )
        skip_reason, notes, channel_labels = self.process(
            recording, steps, job, name, output_folder
        )
        if skip_reason is not None:
            L.info("Skipping %s: %s.", name, skip_reason)
            write_skip(recording_folder, skip_reason)
            notes += f"- {skip_reason}; skipped.\n"
        write_data_process(
            output_folder / f"data_process_preprocessing_{name}.json",
            name="Ephys preprocessing",
            parameters={
                "steps": steps,
                "motion_correction": self.config.motion_correction.model_dump(mode="json"),
            },
            outputs={} if channel_labels is None else {"channel_labels": channel_labels},
            notes=notes,
            start=start,
        )

    def process(
        self,
        recording: si.BaseRecording,
        steps: dict[str, dict],
        job: dict,
        name: str,
        output_folder: Path,
    ) -> tuple[str | None, str, list[str] | None]:
        """Preprocess and save one recording; return why it was skipped, notes and its labels."""
        init = self.config.initialize
        duration = recording.get_total_duration()
        if duration < init.min_preprocessing_duration and not job.get("debug"):  # ty:ignore[unsupported-operator]
            return f"Recording too short ({duration:.2f} s)", "", None
        processed, notes = apply_steps(recording, steps)
        if processed is None:
            return "Every preprocessing step failed", notes, None
        channel_labels = bad_channel_labels(processed)
        num_removed = recording.get_num_channels() - processed.get_num_channels()
        max_removed = int(init.max_bad_channel_fraction * recording.get_num_channels())
        if (init.remove_bad_channels or init.remove_out_channels) and num_removed >= max_removed:
            return f"Too many bad channels ({num_removed})", notes, channel_labels
        return None, notes + self.save(processed, name, output_folder), channel_labels

    def save(self, processed: si.BaseRecording, name: str, output_folder: Path) -> str:
        """Save the preprocessed traces and the files that reload them; return notes."""
        binary = processed.save(folder=output_folder / f"preprocessed_{name}")
        dump_recording(binary, output_folder, f"binary_{name}", relative_to=output_folder)
        # The lazy chain points at the raw input, so it keeps absolute paths.
        dump_recording(processed, output_folder, f"preprocessed_{name}", relative_to=None)
        if not self.config.motion_correction.compute:
            return ""
        corrected, notes = estimate_motion(
            binary, processed, self.config.motion_correction, output_folder / f"motion_{name}"
        )
        if corrected is not None:
            dump_recording(corrected, output_folder, f"motioncorrected_{name}", relative_to=None)
        return notes

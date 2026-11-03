"""Dispatch stage: split an NWB file's raw recordings into the jobs later stages process."""

import logging
from pathlib import Path
from typing import ClassVar

import entitysdk
import numpy as np
import probeinterface as pi
import spikeinterface as si
import spikeinterface.extractors as se
from pynwb import NWBHDF5IO
from spikeinterface.extractors.nwbextractors import NwbRecordingExtractor

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._01_dispatch.blocks import JobDispatch
from obi_one.scientific.tasks.aind_ephys._01_dispatch.config import AINDEPhysDispatchSingleConfig
from obi_one.scientific.tasks.aind_ephys.utils import write_jobs

L = logging.getLogger(__name__)

# Timestamp glitches tolerated before a recording's times are reset, as in the AIND pipeline.
ACCEPTED_NEGATIVE_DEVIATION_MS = 0.2
MAX_NUM_NEGATIVE_TIMESTAMPS = 10
ABS_MAX_TIMESTAMPS_DEVIATION_MS = 2
MAX_FRACTION_ZERO_TIMESTAMPS_DIFF = 0.02


def set_probe_from_electrode_groups(nwb_path: Path, recording: si.BaseRecording) -> None:
    """Give the recording's probe the name and description of its NWB device.

    The NWB reader recovers only the contact positions, which the NWB export stages need to map
    back to devices. The reader's probe is kept when the groups name no single device.
    """
    group_names = np.unique(recording.get_channel_groups())
    with NWBHDF5IO(str(nwb_path), "r", load_namespaces=True) as io:
        nwbfile = io.read()
        groups = [nwbfile.electrode_groups.get(str(name)) for name in group_names]
        devices = {group.device for group in groups if group is not None}
        if None in groups or len(devices) != 1:
            L.warning(
                "No single NWB device for groups %s; keeping the reader's probe.", group_names
            )
            return
        device = devices.pop()
        locations = {group.location for group in groups}

    probe = pi.Probe(ndim=2, si_units="um", name=device.name, manufacturer=device.manufacturer)
    probe.set_contacts(
        positions=recording.get_channel_locations(),
        shapes="circle",
        shape_params={"radius": 5},
        contact_ids=recording.get_channel_ids(),
    )
    probe.set_device_channel_indices(np.arange(recording.get_num_channels()))
    if len(group_names) > 1:
        probe.set_shank_ids(recording.get_channel_groups())
    if device.description is not None:
        probe.annotate(description=device.description)
    if len(locations) == 1:
        probe.annotate(electrode_group_location=locations.pop())
    recording.set_probe(probe, in_place=True)


def read_nwb_recordings(
    nwb_path: Path, electrical_series_path: str | None, min_sampling_frequency: float
) -> dict[str, si.BaseRecording]:
    """The raw recordings in the NWB file's acquisition, by recording name."""
    if electrical_series_path is not None:
        series_paths = [electrical_series_path]
    else:
        series_paths = [
            path
            for path in NwbRecordingExtractor.fetch_available_electrical_series_paths(nwb_path)
            if "acquisition" in path
        ]

    recordings = {}
    for series_path in series_paths:
        recording = se.read_nwb_recording(nwb_path, electrical_series_path=series_path)
        if recording.sampling_frequency < min_sampling_frequency:
            L.info("Skipping %s, probably LFP at %s Hz.", series_path, recording.sampling_frequency)
            continue
        if not recording.has_channel_location():
            L.info("Skipping %s, whose electrodes have no locations.", series_path)
            continue
        set_probe_from_electrode_groups(nwb_path, recording)
        recordings[f"block0_{series_path.replace('/', '-')}_recording"] = recording
    if not recordings:
        msg = f"No raw recording with channel locations found in {nwb_path}."
        raise ValueError(msg)
    return recordings


def timestamps_problem(recording: si.BaseRecording) -> str | None:
    """Why the recording's timestamps cannot be trusted, or None if they can."""
    for segment_index in range(recording.get_num_segments()):
        times_diff_ms = np.diff(recording.get_times(segment_index=segment_index)) * 1000
        num_negative = int(np.sum(times_diff_ms < -ACCEPTED_NEGATIVE_DEVIATION_MS))
        if num_negative > MAX_NUM_NEGATIVE_TIMESTAMPS:
            return f"{num_negative} timestamp diffs below -{ACCEPTED_NEGATIVE_DEVIATION_MS} ms"
        max_diff_ms = float(np.max(np.abs(times_diff_ms)))
        if max_diff_ms > ABS_MAX_TIMESTAMPS_DEVIATION_MS:
            return f"timestamp diff of {max_diff_ms} ms"
        num_zero = int(np.sum(times_diff_ms == 0))
        if num_zero >= MAX_FRACTION_ZERO_TIMESTAMPS_DIFF * len(times_diff_ms):
            return f"{num_zero}/{len(times_diff_ms)} zero timestamp diffs"
    return None


def clip_segments(recording: si.BaseRecording, duration_s: float) -> si.BaseRecording:
    """Clip every segment of the recording to its first ``duration_s`` seconds."""
    num_frames = int(duration_s * recording.sampling_frequency)
    segments = [
        segment.frame_slice(start_frame=0, end_frame=min(num_frames, segment.get_num_samples()))
        for segment in si.split_recording(recording)
    ]
    return si.append_recordings(segments)


def dispatch_jobs(nwb_path: Path, params: JobDispatch) -> list[dict]:
    """One job per recording, segment and probe group of an NWB file.

    Each job holds the recording serialized relative to the NWB file's folder, which it records
    as ``input_folder``. Only metadata is read, so this is cheap.
    """
    nwb_path = Path(nwb_path).resolve()
    input_folder = nwb_path.parent
    recordings = read_nwb_recordings(
        nwb_path, params.electrical_series_path, params.min_sampling_frequency
    )

    jobs = []
    for recording_name, full_recording in recordings.items():
        duration = full_recording.get_total_duration()
        if params.min_recording_duration is not None and duration < params.min_recording_duration:
            L.info("Skipping %s, which lasts only %.2f s.", recording_name, duration)
            continue
        segments = si.split_recording(full_recording) if params.split_segments else [full_recording]
        for segment_index, segment in enumerate(segments):
            recording = segment
            segment_name = (
                f"{recording_name}{segment_index + 1}" if params.split_segments else recording_name
            )
            problem = None if params.skip_timestamps_check else timestamps_problem(recording)
            if problem is not None:
                L.info("Resetting the timestamps of %s: %s.", segment_name, problem)
                recording.reset_times()
            if params.debug:
                recording = clip_segments(recording, params.debug_duration)

            if params.split_groups and len(np.unique(recording.get_channel_groups())) > 1:
                groups = {
                    f"{segment_name}_group{group}": group_recording
                    for group, group_recording in recording.split_by("group").items()
                }
            else:
                groups = {segment_name: recording}

            for job_recording_name, group_recording in groups.items():
                L.info(
                    "Job %s: %.2f s, %d channels.",
                    job_recording_name,
                    group_recording.get_total_duration(),
                    group_recording.get_num_channels(),
                )
                jobs.append(
                    {
                        "session_name": nwb_path.stem,
                        "recording_name": job_recording_name,
                        "recording_dict": group_recording.to_dict(
                            recursive=True, relative_to=input_folder
                        ),
                        "input_folder": str(input_folder),
                        "skip_times": problem is not None,
                        "duration": round(group_recording.get_total_duration(), 2),
                        "debug": params.debug,
                    }
                )

    if not jobs:
        msg = f"Every recording in {nwb_path} was too short to dispatch."
        raise ValueError(msg)
    return jobs


class AINDEPhysDispatchTask(Task):
    """Write one ``job_<i>.json`` per recording, segment and probe group of an NWB file.

    Each job holds the recording serialized relative to the NWB file's folder, which it records as
    ``input_folder``, so later stages can load it from wherever that folder is.
    """

    name: ClassVar[str] = "AIND Ephys Job Dispatch"
    description: ClassVar[str] = "Splits an NWB file's extracellular recordings into jobs."

    config: AINDEPhysDispatchSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ruff: ignore[unused-method-argument]  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> Path:
        init = self.config.initialize
        jobs = dispatch_jobs(init.nwb_path, init)
        output_folder = Path(self.config.coordinate_output_root)
        write_jobs(jobs, output_folder)
        L.info("Wrote %d job files into %s.", len(jobs), output_folder)
        return output_folder

"""The less-travelled paths of the AIND ephys stages, on small synthetic recordings."""

import json
import sys
import uuid
from pathlib import Path
from typing import get_args
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytest.importorskip("spikeinterface")

import spikeinterface as si
import spikeinterface.sorters as ss
from spikeinterface.preprocessing.motion import motion_options_preset

from obi_one.core.info import Info
from obi_one.scientific.from_id.extracellular_recording_from_id import (
    ExtracellularRecordingFromID,
)
from obi_one.scientific.tasks.aind_ephys._01_dispatch import task as dispatch_task
from obi_one.scientific.tasks.aind_ephys._01_dispatch.blocks import JobDispatch
from obi_one.scientific.tasks.aind_ephys._01_dispatch.task import (
    clip_segments,
    dispatch_jobs,
    read_nwb_recordings,
    set_probe_from_electrode_groups,
    timestamps_problem,
)
from obi_one.scientific.tasks.aind_ephys._02_preprocessing import task as preprocessing_task
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import MotionCorrection
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.task import (
    AINDEPhysPreprocessingTask,
    apply_steps,
    bad_channel_labels,
    clip,
    split_concatenated,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting import task as sorting_task
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.blocks import (
    Kilosort4Sorter,
    LupinSorter,
    SpykingCircus2Sorter,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.config import (
    AINDEPhysSpikeSortingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.task import (
    SORTER_LOG_FILE_NAME,
    AINDEPhysSpikeSortingTask,
    read_kilosort4_motion,
)
from obi_one.scientific.tasks.aind_ephys._04_postprocessing import task as postprocessing_task
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.config import (
    AINDEPhysPostprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.task import (
    AINDEPhysPostprocessingTask,
    motion_corrected,
)
from obi_one.scientific.tasks.aind_ephys._05_curation import task as curation_task
from obi_one.scientific.tasks.aind_ephys._05_curation.config import AINDEPhysCurationSingleConfig
from obi_one.scientific.tasks.aind_ephys._05_curation.task import (
    LIGHTWEIGHT_UNITREFINE_CLASSIFIERS,
    AINDEPhysCurationTask,
    bombcell_thresholds,
    unitrefine_classifiers,
)
from obi_one.scientific.tasks.aind_ephys._06_visualization.config import (
    AINDEPhysVisualizationSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._07_results_collector.config import (
    AINDEPhysResultsCollectorSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys.blocks import JobKwargs, MotionPreset
from obi_one.scientific.tasks.aind_ephys.toy_recording import (
    ELECTRICAL_SERIES_NAME,
    write_toy_nwb,
)
from obi_one.scientific.tasks.aind_ephys.utils import (
    ERROR_FILE_NAME,
    dump_recording,
    load_dumped_recording,
    load_recording,
    load_sorting,
    read_jobs,
    remove_outputs,
    write_jobs,
    write_skip,
)

FS = 30000.0
SINGLE_JOB = JobKwargs(n_jobs=1)
INFO = Info(campaign_name="Test campaign", campaign_description="Test campaign.")
SERIES_PATH = f"acquisition/{ELECTRICAL_SERIES_NAME}"
RECORDING_NAME = "rec"


@pytest.fixture(scope="module")
def nwb_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("aind_ephys_paths") / "toy.nwb"
    write_toy_nwb(path)
    return path


def small_recording(durations=(2.0,), num_channels=4) -> si.BaseRecording:
    return si.generate_recording(durations=list(durations), num_channels=num_channels, seed=0)


def preprocessed_folder(root: Path, durations=(2.0,), num_channels=4) -> Path:
    """A folder laid out as the preprocessing stage writes it, holding one recording."""
    folder = root / "preprocessing"
    binary = small_recording(durations, num_channels).save(
        folder=folder / f"preprocessed_{RECORDING_NAME}"
    )
    dump_recording(binary, folder, f"binary_{RECORDING_NAME}", relative_to=folder)
    return folder


def fake_run_sorter(recording_durations=(2.0,)):
    """Stands in for ``ss.run_sorter``: writes the sorter's log and returns a sorting."""

    def run(_sorter_name, _recording, *, folder, **_params):
        Path(folder).mkdir(parents=True)
        (Path(folder) / SORTER_LOG_FILE_NAME).write_text("{}")
        return si.generate_sorting(
            num_units=2, durations=list(recording_durations), sampling_frequency=FS, seed=0
        )

    return run


def preprocessing_form(root: Path, **kwargs) -> AINDEPhysPreprocessingSingleConfig:
    form = AINDEPhysPreprocessingSingleConfig(
        info=INFO,
        **{
            "job_kwargs": SINGLE_JOB,
            "motion_correction": MotionCorrection(compute=False),
            **kwargs,
        },
    )
    form.coordinate_output_root = root
    return form


def sorting_form(root: Path, sorter=None, **initialize) -> AINDEPhysSpikeSortingSingleConfig:
    form = AINDEPhysSpikeSortingSingleConfig(
        info=INFO,
        initialize=AINDEPhysSpikeSortingSingleConfig.Initialize(**initialize),
        job_kwargs=SINGLE_JOB,
        sorter=sorter or SpykingCircus2Sorter(),
    )
    form.coordinate_output_root = root
    return form


def recording_with_time_diffs(diffs: np.ndarray) -> si.BaseRecording:
    recording = si.NumpyRecording(
        [np.zeros((len(diffs) + 1, 2), dtype="float32")], sampling_frequency=FS
    )
    recording.set_times(np.concatenate([[0.0], np.cumsum(diffs)]), with_warning=False)
    return recording


class TestDispatch:
    def test_series_below_the_sampling_frequency_are_not_dispatched(self, nwb_path):
        with pytest.raises(ValueError, match="No raw recording"):
            read_nwb_recordings(nwb_path, None, min_sampling_frequency=FS * 10)

    def test_a_named_series_is_read(self, nwb_path):
        recordings = read_nwb_recordings(nwb_path, SERIES_PATH, min_sampling_frequency=FS / 2)

        assert list(recordings) == [f"block0_{SERIES_PATH.replace('/', '-')}_recording"]

    def test_series_without_channel_locations_are_not_dispatched(self, nwb_path):
        no_locations = si.NumpyRecording(
            [np.zeros((10, 2), dtype="float32")], sampling_frequency=FS
        )
        with (
            patch.object(dispatch_task.se, "read_nwb_recording", return_value=no_locations),
            pytest.raises(ValueError, match="No raw recording"),
        ):
            read_nwb_recordings(nwb_path, SERIES_PATH, min_sampling_frequency=FS / 2)

    def test_the_readers_probe_is_kept_when_the_groups_name_no_device(self, nwb_path):
        recording = small_recording()
        recording.set_channel_groups(np.full(recording.get_num_channels(), "unknown", dtype=object))
        probe = recording.get_probe()

        set_probe_from_electrode_groups(nwb_path, recording)

        assert recording.get_probe().name == probe.name

    @pytest.mark.parametrize(
        ("index_and_diff", "reason"),
        [
            (None, None),
            ((range(20), -0.001), "below"),
            ((range(1), 0.005), "timestamp diff of"),
            ((range(200), 0.0), "zero timestamp diffs"),
        ],
    )
    def test_timestamps_problem(self, index_and_diff, reason):
        diffs = np.full(2999, 1 / FS)
        if index_and_diff is not None:
            indices, diff = index_and_diff
            diffs[list(indices)] = diff

        problem = timestamps_problem(recording_with_time_diffs(diffs))

        assert problem is None if reason is None else reason in problem

    def test_clip_segments_keeps_each_segments_start(self):
        clipped = clip_segments(small_recording(durations=(2.0, 1.0)), duration_s=1.5)

        assert [clipped.get_num_samples(i) for i in range(2)] == [
            int(1.5 * clipped.sampling_frequency),
            int(1.0 * clipped.sampling_frequency),
        ]

    def test_debug_clips_each_job(self, nwb_path):
        (job,) = dispatch_jobs(nwb_path, JobDispatch(debug=True, debug_duration=2.0))

        assert job["debug"] is True
        assert job["duration"] == pytest.approx(2.0)

    def test_recordings_below_the_minimum_duration_are_not_dispatched(self, nwb_path):
        with pytest.raises(ValueError, match="too short"):
            dispatch_jobs(nwb_path, JobDispatch(min_recording_duration=1000.0))

    def test_recordings_with_bad_timestamps_are_flagged(self, nwb_path):
        with patch.object(dispatch_task, "timestamps_problem", return_value="bad"):
            (job,) = dispatch_jobs(nwb_path, JobDispatch())

        assert job["skip_times"] is True

    def test_groups_and_segments_split_into_jobs(self, nwb_path):
        recording = small_recording(durations=(1.0, 1.0), num_channels=4)
        recording.set_channel_groups([0, 0, 1, 1])

        with patch.object(
            dispatch_task, "read_nwb_recordings", return_value={RECORDING_NAME: recording}
        ):
            names = [job["recording_name"] for job in dispatch_jobs(nwb_path, JobDispatch())]
            unsplit = dispatch_jobs(nwb_path, JobDispatch(split_segments=False, split_groups=False))

        assert names == [
            f"{RECORDING_NAME}{segment}_group{group}" for segment in (1, 2) for group in (0, 1)
        ]
        assert [job["recording_name"] for job in unsplit] == [RECORDING_NAME]


class TestPreprocessingHelpers:
    def test_clip_without_bounds_returns_the_recording(self):
        recording = small_recording()

        assert clip(recording, None, None) is recording

    def test_clip_keeps_the_window(self):
        clipped = clip(small_recording(), 0.5, 1.5)

        assert clipped.get_total_duration() == pytest.approx(1.0, abs=2 / FS)

    def test_clip_leaves_multi_segment_recordings_whole(self):
        recording = small_recording(durations=(1.0, 1.0))

        assert clip(recording, 0.5, None) is recording

    def test_apply_steps_drops_the_last_step_after_a_failure(self):
        steps = {"highpass_filter": {"freq_min": 300.0}, "not_a_step": {}}

        processed, notes = apply_steps(small_recording(), steps)

        assert processed is not None
        assert "Dropped not_a_step" in notes
        assert "not_a_step" in steps

    def test_apply_steps_gives_up_when_every_step_fails(self):
        processed, notes = apply_steps(small_recording(), {"not_a_step": {}})

        assert processed is None
        assert "Dropped not_a_step" in notes

    def test_bad_channel_labels_without_the_step(self):
        assert bad_channel_labels(small_recording()) is None

    def test_bad_channel_labels_are_read_from_the_chain(self):
        recording = small_recording(num_channels=8)
        processed = si.preprocessing.detect_and_remove_bad_channels(recording, method="std")

        assert len(bad_channel_labels(processed)) == recording.get_num_channels()

    def test_split_concatenated_restores_the_segments(self):
        recording = small_recording(durations=(1.0, 2.0))
        lengths = [recording.get_num_samples(i) for i in range(2)]

        split = split_concatenated(si.concatenate_recordings([recording]), lengths)

        assert [split.get_num_samples(i) for i in range(2)] == lengths

    def test_the_pipeline_follows_the_chosen_strategies(self):
        form = AINDEPhysPreprocessingSingleConfig(
            info=INFO,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                nwb_path=Path("toy.nwb"), filter_type="bandpass", denoising_strategy="destripe"
            ),
        )

        steps = form.preprocessing_pipeline(has_inter_sample_shift=True)

        assert list(steps) == [
            "phase_shift",
            "bandpass_filter",
            "detect_and_remove_bad_channels",
            "highpass_spatial_filter",
        ]

    def test_motion_windows_scale_with_the_probe_span(self):
        scaled = MotionCorrection(win_step_norm=0.1, win_scale_norm=0.2).estimate_motion_dict(
            1000.0
        )
        rigid = MotionCorrection(win_step_norm=None, win_scale_norm=None).estimate_motion_dict(
            1000.0
        )

        assert scaled["win_step_um"] == pytest.approx(100.0)
        assert scaled["win_scale_um"] == pytest.approx(200.0)
        assert "win_step_um" not in rigid

    def test_job_kwargs_pass_on_the_multiprocessing_context(self):
        assert JobKwargs(mp_context="spawn").to_dict()["mp_context"] == "spawn"
        assert "mp_context" not in JobKwargs().to_dict()


class TestPreprocessingTask:
    def test_too_many_removed_channels_skip_the_recording(self, nwb_path, tmp_path):
        form = preprocessing_form(
            tmp_path,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                nwb_path=nwb_path, min_preprocessing_duration=0.0, max_bad_channel_fraction=0.0
            ),
        )

        folder = AINDEPhysPreprocessingTask(config=form).execute()

        (skipped,) = folder.glob("preprocessed_*")
        assert "Too many bad channels" in (skipped / ERROR_FILE_NAME).read_text()

    def test_failing_every_step_skips_the_recording(self, nwb_path, tmp_path):
        form = preprocessing_form(
            tmp_path,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                nwb_path=nwb_path, min_preprocessing_duration=0.0
            ),
        )

        with patch.object(preprocessing_task, "apply_steps", return_value=(None, "- Failed.\n")):
            folder = AINDEPhysPreprocessingTask(config=form).execute()

        (skipped,) = folder.glob("preprocessed_*")
        assert "Every preprocessing step failed" in (skipped / ERROR_FILE_NAME).read_text()

    def test_motion_is_estimated_and_applied(self, nwb_path, tmp_path):
        form = preprocessing_form(
            tmp_path,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                nwb_path=nwb_path, min_preprocessing_duration=0.0
            ),
            motion_correction=MotionCorrection(apply=True),
        )
        # The real estimate segfaults under pytest on macOS, though not when the task runs alone.
        motion = si.Motion(
            displacement=np.zeros((10, 1)),
            temporal_bins_s=np.arange(10) + 0.5,
            spatial_bins_um=np.array([0.0]),
        )

        with patch.object(
            preprocessing_task.spre, "compute_motion", return_value=motion
        ) as compute:
            folder = AINDEPhysPreprocessingTask(config=form).execute()

        assert compute.call_args.kwargs["preset"] == form.motion_correction.preset
        assert list(folder.glob("motioncorrected_*"))

    @pytest.mark.skipif(sys.platform == "darwin", reason="Segfaults under pytest on macOS.")
    def test_the_default_preset_runs_in_the_launch_jobs_packages(self, nwb_path, tmp_path):
        form = preprocessing_form(
            tmp_path,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                nwb_path=nwb_path, min_preprocessing_duration=0.0
            ),
            motion_correction=MotionCorrection(),
        )

        folder = AINDEPhysPreprocessingTask(config=form).execute()

        (record,) = folder.glob("data_process_preprocessing_*.json")
        assert not json.loads(record.read_text())["notes"]
        assert list(folder.glob("motion_*/motion/displacement_seg0.npy"))

    @pytest.mark.parametrize("preset", get_args(MotionPreset))
    def test_the_offered_presets_do_not_need_torch(self, preset):
        assert "dredge" not in motion_options_preset[preset]["estimate_motion_kwargs"]["method"]

    def test_a_failed_motion_estimate_is_noted(self, nwb_path, tmp_path):
        form = preprocessing_form(
            tmp_path,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                nwb_path=nwb_path, min_preprocessing_duration=0.0
            ),
            motion_correction=MotionCorrection(apply=True),
        )

        with patch.object(preprocessing_task.spre, "compute_motion", return_value=None):
            folder = AINDEPhysPreprocessingTask(config=form).execute()

        (record,) = folder.glob("data_process_preprocessing_*.json")
        assert "Motion estimation failed" in json.loads(record.read_text())["notes"]
        assert not list(folder.glob("motioncorrected_*"))

    def test_a_recording_entity_needs_a_db_client(self, tmp_path):
        form = preprocessing_form(
            tmp_path,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                recording=ExtracellularRecordingFromID(id_str=str(uuid.uuid4()))
            ),
        )

        with pytest.raises(ValueError, match="db_client"):
            AINDEPhysPreprocessingTask(config=form).execute()


class TestSortingTask:
    def test_an_empty_input_folder_is_an_error(self, tmp_path):
        form = sorting_form(tmp_path / "sorting", preprocessing_output_path=tmp_path)

        with pytest.raises(FileNotFoundError, match="preprocessed_"):
            AINDEPhysSpikeSortingTask(config=form).execute()

    def test_recordings_preprocessing_skipped_are_skipped(self, tmp_path):
        write_skip(tmp_path / f"preprocessed_{RECORDING_NAME}", "Too short")
        form = sorting_form(tmp_path / "sorting", preprocessing_output_path=tmp_path)

        folder = AINDEPhysSpikeSortingTask(config=form).execute()

        skip = folder / f"spikesorted_{RECORDING_NAME}" / ERROR_FILE_NAME
        assert "Preprocessing skipped" in skip.read_text()

    def test_a_failed_sorting_stops_the_task_by_default(self, tmp_path):
        form = sorting_form(
            tmp_path / "sorting", preprocessing_output_path=preprocessed_folder(tmp_path)
        )

        with (
            patch.object(sorting_task.ss, "run_sorter", side_effect=RuntimeError("no sorter")),
            pytest.raises(RuntimeError, match="no sorter"),
        ):
            AINDEPhysSpikeSortingTask(config=form).execute()

    def test_a_failed_sorting_can_skip_the_recording(self, tmp_path):
        form = sorting_form(
            tmp_path / "sorting",
            preprocessing_output_path=preprocessed_folder(tmp_path),
            raise_if_fails=False,
        )

        def fail(_sorter_name, _recording, *, folder, **_params):
            Path(folder).mkdir(parents=True)
            (Path(folder) / SORTER_LOG_FILE_NAME).write_text("{}")
            msg = "no sorter"
            raise RuntimeError(msg)

        with patch.object(sorting_task.ss, "run_sorter", side_effect=fail):
            folder = AINDEPhysSpikeSortingTask(config=form).execute()

        sorted_folder = folder / f"spikesorted_{RECORDING_NAME}"
        assert "spykingcircus2 failed" in (sorted_folder / ERROR_FILE_NAME).read_text()
        assert (sorted_folder / SORTER_LOG_FILE_NAME).exists()

    def test_motion_correction_can_be_turned_off(self, tmp_path):
        form = sorting_form(
            tmp_path / "sorting",
            preprocessing_output_path=preprocessed_folder(tmp_path),
            skip_motion_correction=True,
            min_drift_channels=0,
        )

        with patch.object(sorting_task.ss, "run_sorter", side_effect=fake_run_sorter()) as run:
            AINDEPhysSpikeSortingTask(config=form).execute()

        assert run.call_args.kwargs[SpykingCircus2Sorter.motion_correction_parameter] is False

    def test_segments_are_sorted_together_and_split_back(self, tmp_path):
        form = sorting_form(
            tmp_path / "sorting",
            preprocessing_output_path=preprocessed_folder(tmp_path, durations=(1.0, 1.0)),
        )

        with patch.object(sorting_task.ss, "run_sorter", side_effect=fake_run_sorter()):
            folder = AINDEPhysSpikeSortingTask(config=form).execute()

        sorting = load_sorting(folder / f"spikesorted_{RECORDING_NAME}")
        assert sorting.get_num_segments() == 2

    def test_kilosorts_motion_estimate_is_saved(self, tmp_path):
        form = sorting_form(
            tmp_path / "sorting",
            sorter=Kilosort4Sorter(),
            preprocessing_output_path=preprocessed_folder(tmp_path),
            min_drift_channels=0,
        )
        motion = MagicMock()

        with (
            patch.object(sorting_task.ss, "run_sorter", side_effect=fake_run_sorter()),
            patch.object(sorting_task, "read_kilosort4_motion", return_value=motion),
        ):
            folder = AINDEPhysSpikeSortingTask(config=form).execute()

        motion.save.assert_called_once_with(folder / f"spikesortedmotion_{RECORDING_NAME}")

    def test_without_an_input_a_toy_recording_is_sorted(self, tmp_path):
        form = sorting_form(tmp_path / "sorting")

        with patch.object(AINDEPhysSpikeSortingTask, "sort") as sort:
            AINDEPhysSpikeSortingTask(config=form).execute()

        source, name, _output = sort.call_args.args
        assert source.is_relative_to(tmp_path / "sorting" / "toy_input")
        assert (source / f"preprocessed_{name}").is_dir()

    def test_read_kilosort4_motion(self, tmp_path):
        ops = {
            "dshift": np.zeros((10, 3)),
            "batch_size": 6000,
            "fs": FS,
            "yblk": np.array([0.0, 100.0, 200.0]),
        }
        np.save(tmp_path / "ops.npy", ops, allow_pickle=True)

        motion = read_kilosort4_motion(tmp_path, small_recording())

        assert motion.displacement[0].shape == (10, 3)
        assert motion.temporal_bins_s[0][0] == pytest.approx(0.1)
        assert motion.temporal_bins_s[0][-1] < 2.0

    @pytest.mark.parametrize(
        ("sorter", "sorter_name"),
        [(Kilosort4Sorter(), "kilosort4"), (LupinSorter(), "lupin")],
    )
    def test_sorters_only_set_parameters_spikeinterface_knows(self, sorter, sorter_name):
        if sorter_name == "kilosort4":
            # spikeinterface reads these parameters from the package, an optional extra.
            pytest.importorskip("kilosort")
        assert sorter.sorter_name == sorter_name
        assert set(sorter.to_dict()) <= set(ss.get_default_sorter_params(sorter_name))


class TestPostprocessingTask:
    def form(self, root: Path) -> AINDEPhysPostprocessingSingleConfig:
        form = AINDEPhysPostprocessingSingleConfig(
            initialize=AINDEPhysPostprocessingSingleConfig.Initialize(
                preprocessing_output_path=root, spikesort_output_path=root
            ),
            job_kwargs=SINGLE_JOB,
        )
        form.coordinate_output_root = root / "postprocessing"
        return form

    def test_an_empty_input_folder_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="spikesorted_"):
            AINDEPhysPostprocessingTask(config=self.form(tmp_path)).execute()

    def test_recordings_sorting_skipped_are_skipped(self, tmp_path):
        write_skip(tmp_path / f"spikesorted_{RECORDING_NAME}", "No sorter")

        folder = AINDEPhysPostprocessingTask(config=self.form(tmp_path)).execute()

        skip = folder / f"postprocessed_{RECORDING_NAME}.zarr" / ERROR_FILE_NAME
        assert "Spike sorting skipped" in skip.read_text()

    def test_motion_correction_reuses_the_preprocessing_estimate(self, tmp_path):
        recording = small_recording()
        corrected = MagicMock()
        info = {"motion": "motion", "parameters": {"interpolate_motion_kwargs": {"border": 1}}}

        with (
            patch.object(postprocessing_task.spre, "load_motion_info", return_value=info),
            patch.object(
                postprocessing_task, "interpolate_motion", return_value=corrected
            ) as interpolate,
        ):
            assert motion_corrected(recording, tmp_path) is corrected

        assert interpolate.call_args.kwargs == {"motion": "motion", "border": 1}
        corrected.reset_times.assert_called_once()


class TestCuration:
    def form(self, root: Path) -> AINDEPhysCurationSingleConfig:
        form = AINDEPhysCurationSingleConfig(
            initialize=AINDEPhysCurationSingleConfig.Initialize(postprocessing_output_path=root),
            job_kwargs=SINGLE_JOB,
        )
        form.coordinate_output_root = root / "curation"
        return form

    def test_an_empty_input_folder_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="postprocessed_"):
            AINDEPhysCurationTask(config=self.form(tmp_path)).execute()

    def test_recordings_postprocessing_skipped_are_passed_over(self, tmp_path):
        write_skip(tmp_path / f"postprocessed_{RECORDING_NAME}.zarr", "No sorting")

        with patch.object(AINDEPhysCurationTask, "curate") as curate:
            AINDEPhysCurationTask(config=self.form(tmp_path)).execute()

        curate.assert_not_called()

    @pytest.mark.parametrize(
        ("metric_names", "expected"),
        [
            ({"heavy", "sua", "light", "light_sua"}, ("noise", "sua")),
            ({"light", "light_sua"}, LIGHTWEIGHT_UNITREFINE_CLASSIFIERS),
            (set(), None),
        ],
    )
    def test_unitrefine_falls_back_on_the_lightweight_classifiers(self, metric_names, expected):
        required = {
            "noise": ["heavy"],
            "sua": ["sua"],
            LIGHTWEIGHT_UNITREFINE_CLASSIFIERS[0]: ["light"],
            LIGHTWEIGHT_UNITREFINE_CLASSIFIERS[1]: ["light_sua"],
        }

        with patch.object(
            curation_task.scur,
            "get_required_metrics_from_model",
            side_effect=lambda repo_id, trust_model: required[repo_id],  # ruff: ignore[unused-lambda-argument]
        ):
            assert unitrefine_classifiers("noise", "sua", metric_names) == expected

    def test_bombcell_drops_a_missing_metric(self):
        thresholds = {"noise": {"a": {"min": 1}, "b": {"min": 2}}}

        kept = bombcell_thresholds(thresholds, {"a"})

        assert kept == {"noise": {"a": {"min": 1}}}
        assert "b" in thresholds["noise"]

    def test_bombcell_is_skipped_when_too_many_metrics_are_missing(self):
        thresholds = {"noise": {"a": {"min": 1}, "b": {"min": 2}}}

        assert bombcell_thresholds(thresholds, set()) is None


class TestUtils:
    def test_jobs_are_read_in_index_order(self, tmp_path):
        jobs = [{"index": index} for index in range(12)]
        write_jobs(jobs, tmp_path)

        assert read_jobs(tmp_path) == jobs

    def test_a_folder_without_jobs_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="job_"):
            read_jobs(tmp_path)

    def test_a_recording_that_is_not_json_able_is_pickled(self, tmp_path):
        binary = small_recording().save(folder=tmp_path / "binary")

        with patch.object(
            type(binary), "check_serializability", side_effect=lambda kind: kind != "json"
        ):
            path = dump_recording(binary, tmp_path, "dump", relative_to=tmp_path)

        assert path.suffix == ".pkl"
        assert load_dumped_recording(tmp_path, "dump").get_num_channels() == 4

    def test_a_missing_dump_is_an_error(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="missing"):
            load_dumped_recording(tmp_path, "missing")

    def test_loading_the_wrong_kind_of_object_is_an_error(self, tmp_path):
        recording_folder = tmp_path / "recording"
        sorting_folder = tmp_path / "sorting"
        small_recording().save(folder=recording_folder)
        si.generate_sorting(num_units=2, durations=[1.0], seed=0).save(folder=sorting_folder)

        with pytest.raises(TypeError, match="Expected a recording"):
            load_recording(sorting_folder)
        with pytest.raises(TypeError, match="Expected a sorting"):
            load_sorting(recording_folder)

    def test_remove_outputs_takes_files_and_folders(self, tmp_path):
        file = tmp_path / "file"
        file.write_text("")
        folder = tmp_path / "folder"
        folder.mkdir()

        remove_outputs(file, folder, tmp_path / "absent")

        assert not file.exists()
        assert not folder.exists()


class TestCapsuleConfigs:
    def test_visualization_params_are_json_able(self, tmp_path):
        form = AINDEPhysVisualizationSingleConfig(
            initialize=AINDEPhysVisualizationSingleConfig.Initialize(
                dispatch_output_path=tmp_path,
                preprocessing_output_path=tmp_path,
                postprocessing_output_path=tmp_path,
                curation_output_path=tmp_path,
            ),
        )

        assert set(json.loads(json.dumps(form.params_dict()))) >= {"timeseries", "drift"}

    def test_results_collector_describes_its_session(self, tmp_path):
        form = AINDEPhysResultsCollectorSingleConfig(
            initialize=AINDEPhysResultsCollectorSingleConfig.Initialize(
                dispatch_output_path=tmp_path,
                preprocessing_output_path=tmp_path,
                spikesort_output_path=tmp_path,
                postprocessing_output_path=tmp_path,
                curation_output_path=tmp_path,
                visualization_output_path=tmp_path,
            ),
        )

        assert form.synthetic_data_description()["name"] == form.initialize.session_name

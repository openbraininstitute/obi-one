"""The AIND ephys pipeline stages, run once in sequence on a toy NWB recording."""

import json
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import spikeinterface as si
from entitysdk.types import AssetLabel, TaskResultType
from pydantic import ValidationError

from obi_one.core.info import Info
from obi_one.core.run_tasks import run_tasks_for_generated_scan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.core.task import Task
from obi_one.scientific.from_id.extracellular_recording_from_id import (
    ExtracellularRecordingFromID,
)
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.aind_ephys._01_dispatch.config import AINDEPhysDispatchScanConfig
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.blocks import MotionCorrection
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingScanConfig,
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.task import AINDEPhysPreprocessingTask
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.blocks import deep_merge
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.spykingcircus2.config import (
    AINDEPhysSpikeSortingSpykingCircus2ScanConfig,
    AINDEPhysSpikeSortingSpykingCircus2SingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.spykingcircus2.task import (
    AINDEPhysSpikeSortingSpykingCircus2Task,
)
from obi_one.scientific.tasks.aind_ephys.blocks import JobKwargs
from obi_one.scientific.tasks.aind_ephys.toy_recording import PROBE_NAME, write_toy_nwb
from obi_one.scientific.tasks.aind_ephys.utils import ERROR_FILE_NAME

NUM_CHANNELS = 32
SINGLE_JOB = JobKwargs(n_jobs=1)
INFO = Info(campaign_name="Test campaign", campaign_description="Test campaign.")
CONFIG_MODULES = [
    f"obi_one.scientific.tasks.aind_ephys.{stage}.config"
    for stage in (
        "_01_dispatch",
        "_02_preprocessing",
        "_03_spikesorting",
        "_03_spikesorting.kilosort4",
        "_03_spikesorting.spykingcircus2",
        "_03_spikesorting.lupin",
    )
]


def run_stage(form, output_root: Path) -> Path:
    scan = GridScanGenerationTask(
        form=form, output_root=output_root, coordinate_directory_option="ZERO_INDEX"
    )
    scan.execute()
    run_tasks_for_generated_scan(scan)
    return output_root / "0"


@pytest.fixture(scope="module")
def stages(tmp_path_factory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("aind_ephys")
    nwb_path = root / "toy.nwb"
    write_toy_nwb(nwb_path, num_channels=NUM_CHANNELS)

    dispatch = run_stage(
        AINDEPhysDispatchScanConfig(
            initialize=AINDEPhysDispatchScanConfig.Initialize(nwb_path=nwb_path)
        ),
        root / "dispatch",
    )
    preprocessing = run_stage(
        AINDEPhysPreprocessingScanConfig(
            info=INFO,
            initialize=AINDEPhysPreprocessingScanConfig.Initialize(
                nwb_path=nwb_path, min_preprocessing_duration=0.0
            ),
            job_kwargs=SINGLE_JOB,
            motion_correction=MotionCorrection(compute=False),
        ),
        root / "preprocessing",
    )
    sorting = run_stage(
        AINDEPhysSpikeSortingSpykingCircus2ScanConfig(
            info=INFO,
            initialize=AINDEPhysSpikeSortingSpykingCircus2ScanConfig.Initialize(
                preprocessing_output_path=preprocessing
            ),
            job_kwargs=SINGLE_JOB,
        ),
        root / "sorting",
    )
    return {
        "root": root,
        "nwb": nwb_path,
        "dispatch": dispatch,
        "preprocessing": preprocessing,
        "sorting": sorting,
    }


def registering_client() -> MagicMock:
    """A db client whose registered entities come back with an id."""
    client = MagicMock()
    client.register_entity.side_effect = lambda entity: entity.model_copy(
        update={"id": uuid.uuid4()}
    )
    return client


def only_name(folder: Path, prefix: str, suffix: str = "") -> str:
    (path,) = folder.glob(f"{prefix}*{suffix}")
    return path.name.removeprefix(prefix).removesuffix(suffix)


class TestStages:
    def test_dispatch_writes_one_job_with_the_probe(self, stages):
        (job_file,) = stages["dispatch"].glob("job_*.json")
        job = json.loads(job_file.read_text())

        recording = si.load(job["recording_dict"], base_folder=Path(job["input_folder"]))

        assert recording.get_num_channels() == NUM_CHANNELS
        assert recording.get_probe().name == PROBE_NAME
        assert job["recording_name"] == "block0_acquisition-ElectricalSeriesRaw_recording1"

    def test_preprocessing_saves_a_reloadable_binary(self, stages):
        folder = stages["preprocessing"]
        name = only_name(folder, "preprocessed_", ".json")

        binary = si.load(folder / f"binary_{name}.json", base_folder=folder)
        record = json.loads((folder / f"data_process_preprocessing_{name}.json").read_text())

        assert binary.get_num_channels() <= NUM_CHANNELS
        assert len(record["outputs"]["channel_labels"]) == NUM_CHANNELS
        assert list(record["parameters"]["steps"]) == [
            "highpass_filter",
            "detect_and_remove_bad_channels",
            "common_reference",
        ]

    def test_preprocessing_dispatches_like_the_dispatch_stage(self, stages):
        (dispatched,) = stages["dispatch"].glob("job_*.json")
        (preprocessed,) = stages["preprocessing"].glob("job_*.json")

        assert json.loads(preprocessed.read_text()) == json.loads(dispatched.read_text())

    @pytest.mark.parametrize("both", [True, False])
    def test_preprocessing_needs_exactly_one_input(self, stages, both):
        recording = ExtracellularRecordingFromID(id_str=str(uuid.uuid4())) if both else None
        with pytest.raises(ValidationError, match="either a recording or an NWB file"):
            AINDEPhysPreprocessingScanConfig(
                info=INFO,
                initialize=AINDEPhysPreprocessingScanConfig.Initialize(
                    recording=recording, nwb_path=stages["nwb"] if both else None
                ),
            )

    def test_preprocessing_downloads_the_recording_entity(self, stages, tmp_path):
        form = AINDEPhysPreprocessingSingleConfig(
            info=INFO,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                recording=ExtracellularRecordingFromID(id_str=str(uuid.uuid4())),
                min_preprocessing_duration=0.0,
            ),
            job_kwargs=SINGLE_JOB,
            motion_correction=MotionCorrection(compute=False),
        )
        form.coordinate_output_root = tmp_path / "preprocessing"

        def download(_self, dest_dir, **_kwargs):
            dest_dir.mkdir(parents=True)
            return Path(shutil.copy(stages["nwb"], dest_dir))

        with patch.object(ExtracellularRecordingFromID, "download_nwb_asset", download):
            folder = AINDEPhysPreprocessingTask(config=form).execute(db_client=object())

        (job_file,) = folder.glob("job_*.json")
        assert json.loads(job_file.read_text())["input_folder"] == str((folder / "input").resolve())
        assert len(list(folder.glob("binary_*.json"))) == 1

    def test_launched_preprocessing_registers_its_folder_without_the_input(self, stages, tmp_path):
        form = AINDEPhysPreprocessingSingleConfig(
            info=INFO,
            initialize=AINDEPhysPreprocessingSingleConfig.Initialize(
                recording=ExtracellularRecordingFromID(id_str=str(uuid.uuid4())),
                min_preprocessing_duration=0.0,
            ),
            job_kwargs=SINGLE_JOB,
            motion_correction=MotionCorrection(compute=False),
        )
        form.coordinate_output_root = tmp_path / "preprocessing"
        db_client = registering_client()

        def download(_self, dest_dir, **_kwargs):
            dest_dir.mkdir(parents=True)
            return Path(shutil.copy(stages["nwb"], dest_dir))

        with (
            patch.object(ExtracellularRecordingFromID, "download_nwb_asset", download),
            patch.object(Task, "_get_execution_activity"),
            patch.object(Task, "_update_execution_activity") as update_activity,
        ):
            AINDEPhysPreprocessingTask(config=form).execute(
                db_client=db_client, execution_activity_id=str(uuid.uuid4())
            )

        result = db_client.register_entity.call_args.args[0]
        upload = db_client.upload_directory.call_args.kwargs
        top_level = {path.parts[0] for path in upload["paths"]}
        assert result.name == INFO.campaign_name
        assert result.task_result_type == TaskResultType.aind_ephys_preprocessing__result
        assert upload["label"] == AssetLabel.task_result
        assert "input" not in top_level
        assert any(name.startswith("binary_") for name in top_level)
        assert update_activity.call_args.kwargs["generated"] == [str(upload["entity_id"])]

    def test_launched_sorting_reads_and_registers_results(self, stages, tmp_path):
        form = AINDEPhysSpikeSortingSpykingCircus2SingleConfig(
            info=INFO,
            initialize=AINDEPhysSpikeSortingSpykingCircus2SingleConfig.Initialize(
                preprocessing_result=TaskResultFromID(id_str=str(uuid.uuid4())),
            ),
            job_kwargs=SINGLE_JOB,
        )
        form.coordinate_output_root = tmp_path / "sorting"
        db_client = registering_client()

        with (
            patch.object(
                TaskResultFromID,
                "download_directory_asset_by_label",
                return_value=stages["preprocessing"],
            ) as download,
            patch.object(AINDEPhysSpikeSortingSpykingCircus2Task, "sort") as sort,
            patch.object(Task, "_get_execution_activity"),
            patch.object(Task, "_update_execution_activity") as update_activity,
        ):
            AINDEPhysSpikeSortingSpykingCircus2Task(config=form).execute(
                db_client=db_client, execution_activity_id=str(uuid.uuid4())
            )

        result = db_client.register_entity.call_args.args[0]
        upload = db_client.upload_directory.call_args.kwargs
        assert download.call_args.args == (AssetLabel.task_result,)
        assert sort.call_args.args[0] == stages["preprocessing"]
        assert result.task_result_type == TaskResultType.aind_ephys_spikesorting__result
        assert update_activity.call_args.kwargs["generated"] == [str(upload["entity_id"])]

    def test_the_input_entities_are_recorded_on_the_task_config(self):
        db_client = object()
        recording = ExtracellularRecordingFromID(id_str=str(uuid.uuid4()))
        result = TaskResultFromID(id_str=str(uuid.uuid4()))
        preprocessing = AINDEPhysPreprocessingScanConfig(
            info=INFO, initialize=AINDEPhysPreprocessingScanConfig.Initialize(recording=recording)
        )
        sorting = AINDEPhysSpikeSortingSpykingCircus2ScanConfig(
            info=INFO,
            initialize=AINDEPhysSpikeSortingSpykingCircus2ScanConfig.Initialize(
                preprocessing_result=result
            ),
        )

        with (
            patch.object(ExtracellularRecordingFromID, "entity", return_value="recording"),
            patch.object(TaskResultFromID, "entity", return_value="result"),
        ):
            assert preprocessing.input_entities(db_client) == ["recording"]
            assert sorting.input_entities(db_client) == ["result"]

    def test_preprocessing_skips_recordings_that_are_too_short(self, stages, tmp_path):
        folder = run_stage(
            AINDEPhysPreprocessingScanConfig(
                info=INFO,
                initialize=AINDEPhysPreprocessingScanConfig.Initialize(nwb_path=stages["nwb"]),
                job_kwargs=SINGLE_JOB,
            ),
            tmp_path / "preprocessing",
        )
        (skipped,) = folder.glob("preprocessed_*")

        assert [path.name for path in skipped.iterdir()] == [ERROR_FILE_NAME]

    def test_preprocessing_reruns_into_the_same_folder(self, stages, tmp_path):
        form = AINDEPhysPreprocessingScanConfig(
            info=INFO,
            initialize=AINDEPhysPreprocessingScanConfig.Initialize(
                nwb_path=stages["nwb"], min_preprocessing_duration=0.0
            ),
            job_kwargs=SINGLE_JOB,
            motion_correction=MotionCorrection(compute=False),
        )

        run_stage(form, tmp_path / "preprocessing")
        folder = run_stage(form, tmp_path / "preprocessing")

        assert len(list(folder.glob("binary_*.json"))) == 1

    def test_sorting_finds_units(self, stages):
        name = only_name(stages["sorting"], "spikesorted_")

        sorting = si.load(stages["sorting"] / f"spikesorted_{name}")

        assert len(sorting.unit_ids) > 0

    def test_sorting_passes_on_skips(self, tmp_path):
        skipped = tmp_path / "preprocessing" / "preprocessed_skipped"
        skipped.mkdir(parents=True)
        (skipped / ERROR_FILE_NAME).write_text("Too many bad channels")

        folder = run_stage(
            AINDEPhysSpikeSortingSpykingCircus2ScanConfig(
                info=INFO,
                initialize=AINDEPhysSpikeSortingSpykingCircus2ScanConfig.Initialize(
                    preprocessing_output_path=tmp_path / "preprocessing"
                ),
            ),
            tmp_path / "sorting",
        )

        assert (folder / "spikesorted_skipped" / ERROR_FILE_NAME).is_file()


class TestHelpers:
    def test_deep_merge_keeps_unset_nested_defaults(self):
        defaults = {"detection": {"method": "matched_filtering", "detect_threshold": 5}, "seed": 1}

        merged = deep_merge(defaults, {"detection": {"detect_threshold": 6}})

        assert merged == {
            "detection": {"method": "matched_filtering", "detect_threshold": 6},
            "seed": 1,
        }
        assert defaults["detection"]["detect_threshold"] == 5


def test_config_modules_do_not_import_spikeinterface():
    script = "\n".join(
        [
            "import sys",
            *(f"import {module}" for module in CONFIG_MODULES),
            'assert "spikeinterface" not in sys.modules',
        ]
    )
    subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        [sys.executable, "-c", script], check=True
    )

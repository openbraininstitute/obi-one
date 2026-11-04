"""Spike sorting stage: sort the spikes of each preprocessed recording."""

import copy
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import entitysdk
import numpy as np
import spikeinterface as si
import spikeinterface.curation as scur
import spikeinterface.sorters as ss
from entitysdk.types import AssetLabel, TaskResultType

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.config import (
    AINDEPhysSpikeSortingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.materialize import (
    materialize_preprocessing_output,
)
from obi_one.scientific.tasks.aind_ephys.registration import register_stage_result
from obi_one.scientific.tasks.aind_ephys.utils import (
    global_job_kwargs,
    load_dumped_recording,
    remove_outputs,
    stage_output_names,
    was_skipped,
    write_data_process,
    write_skip,
)

L = logging.getLogger(__name__)

SORTER_LOG_FILE_NAME = "spikeinterface_log.json"
INPUT_FOLDER_NAME = "input"
TOY_INPUT_FOLDER_NAME = "toy_input"


def deep_merge(defaults: dict, overrides: dict) -> dict:
    """``defaults`` with ``overrides`` applied, merging nested dicts key by key."""
    merged = copy.deepcopy(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def read_kilosort4_motion(sorter_output_folder: Path, recording: si.BaseRecording) -> si.Motion:
    """The motion Kilosort4 estimated, from its ``ops.npy``."""
    ops = np.load(sorter_output_folder / "ops.npy", allow_pickle=True).item()
    displacement = ops["dshift"]
    t_bin = ops["batch_size"] / ops["fs"]
    temporal_bins_s = np.linspace(
        recording.get_start_time() + t_bin / 2,
        recording.get_end_time() - t_bin / 2,
        displacement.shape[0],
    )
    return si.Motion(
        displacement=displacement, temporal_bins_s=temporal_bins_s, spatial_bins_um=ops["yblk"]
    )


class AINDEPhysSpikeSortingTask(Task):
    """Sort every recording of the preprocessing stage into this config's output folder.

    Sorting runs in ``sorter_scratch/<name>/``, which is removed once the sorting is saved. A
    launched task registers the folder, without its inputs, as a TaskResult of the execution
    activity.
    """

    name: ClassVar[str] = "AIND Ephys Spike Sorting"
    description: ClassVar[str] = "Sorts the spikes of preprocessed extracellular recordings."

    config: AINDEPhysSpikeSortingSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,
    ) -> Path:
        output_folder = Path(self.config.coordinate_output_root)
        output_folder.mkdir(parents=True, exist_ok=True)
        source = self.stage_preprocessing_output(output_folder, db_client)
        names = stage_output_names(source, "preprocessed_")
        if not names:
            msg = f"No preprocessed_<name>/ folders in {source}; run the preprocessing stage first."
            raise FileNotFoundError(msg)

        with global_job_kwargs(self.config.job_kwargs.to_dict()):
            for name in names:
                self.sort(source, name, output_folder)
        shutil.rmtree(output_folder / "sorter_scratch", ignore_errors=True)
        if execution_activity_id is not None:
            result = register_stage_result(
                db_client,
                folder=output_folder,
                task_result_type=TaskResultType.aind_ephys_spikesorting__result,
                name=self.config.campaign_name,
                description="Sorted spikes of preprocessed extracellular recordings.",
                excluded=(INPUT_FOLDER_NAME, TOY_INPUT_FOLDER_NAME),
            )
            self._update_execution_activity(
                db_client=db_client,
                execution_activity=self._get_execution_activity(db_client, execution_activity_id),
                generated=[str(result.id)],
            )
        return output_folder

    def stage_preprocessing_output(
        self, output_folder: Path, db_client: entitysdk.client.Client | None
    ) -> Path:
        """The result entity's folder downloaded into ``input/``, the local folder, or a toy one."""
        init = self.config.initialize
        if init.preprocessing_result is not None:
            return init.preprocessing_result.download_directory_asset_by_label(
                AssetLabel.task_result,
                dest_dir=output_folder / INPUT_FOLDER_NAME,
                db_client=db_client,  # ty:ignore[invalid-argument-type]
            )
        if init.preprocessing_output_path is not None:
            return Path(init.preprocessing_output_path)
        return materialize_preprocessing_output(output_folder / TOY_INPUT_FOLDER_NAME)

    def sort(self, source: Path, name: str, output_folder: Path) -> None:
        """Sort one preprocessed recording."""
        start = datetime.now(UTC)
        init = self.config.initialize
        sorter = self.config.sorter
        sorting_folder = output_folder / f"spikesorted_{name}"
        remove_outputs(sorting_folder, output_folder / f"spikesortedmotion_{name}")
        if was_skipped(source / f"preprocessed_{name}"):
            write_skip(sorting_folder, "Preprocessing skipped this recording")
            return

        recording = load_dumped_recording(source, f"binary_{name}")
        concatenated = recording.get_num_segments() > 1
        if concatenated:
            recording = si.concatenate_recordings([recording])

        params = deep_merge(ss.get_default_sorter_params(sorter.sorter_name), sorter.to_dict())
        if init.skip_motion_correction or recording.get_num_channels() < init.min_drift_channels:
            L.info("Sorting %s without motion correction.", name)
            params[sorter.motion_correction_parameter] = False

        work_folder = output_folder / "sorter_scratch" / name
        L.info("Sorting %s with %s.", name, sorter.sorter_name)
        try:
            sorting = ss.run_sorter(
                sorter.sorter_name,
                recording,
                folder=str(work_folder),
                remove_existing_folder=True,
                delete_output_folder=False,
                verbose=False,
                **params,
            )
        except Exception:
            if init.raise_if_fails:
                raise
            L.exception("Sorting %s failed; skipping it.", name)
            write_skip(sorting_folder, f"{sorter.sorter_name} failed")
            shutil.copy2(work_folder / SORTER_LOG_FILE_NAME, sorting_folder)
            return

        num_units = len(sorting.unit_ids)
        sorting = scur.remove_excess_spikes(sorting.remove_empty_units(), recording)
        if concatenated:
            sorting = si.split_sorting(sorting, recording)
        sorting.save(folder=sorting_folder)
        shutil.copy2(work_folder / SORTER_LOG_FILE_NAME, sorting_folder)
        if sorter.sorter_name == "kilosort4" and params["do_correction"]:
            read_kilosort4_motion(work_folder / "sorter_output", recording).save(
                output_folder / f"spikesortedmotion_{name}"
            )

        write_data_process(
            output_folder / f"data_process_spikesorting_{name}.json",
            name="Spike sorting",
            parameters={"sorter_name": sorter.sorter_name, "sorter_params": params},
            outputs={
                "num_units": len(sorting.unit_ids),
                "empty_units": num_units - len(sorting.unit_ids),
            },
            notes=f"{sorter.sorter_name} found {num_units} units.",
            start=start,
        )

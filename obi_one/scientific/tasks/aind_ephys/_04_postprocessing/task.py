"""Postprocessing stage: remove duplicated units, then compute waveforms and quality metrics."""

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, cast

import entitysdk
import spikeinterface as si
import spikeinterface.curation as scur
import spikeinterface.preprocessing as spre
from spikeinterface.sortingcomponents.motion import interpolate_motion

from obi_one.core.task import Task
from obi_one.scientific.tasks.aind_ephys._04_postprocessing.config import (
    AINDEPhysPostprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys.utils import (
    global_job_kwargs,
    load_dumped_recording,
    load_sorting,
    remove_outputs,
    stage_output_names,
    was_skipped,
    write_data_process,
    write_skip,
)

L = logging.getLogger(__name__)


def motion_corrected(recording: si.BaseRecording, motion_folder: Path) -> si.BaseRecording:
    """The recording corrected with the motion the preprocessing stage estimated."""
    motion_info = spre.load_motion_info(motion_folder)
    corrected = interpolate_motion(
        spre.astype(recording, "float32"),
        motion=motion_info["motion"],
        **motion_info["parameters"]["interpolate_motion_kwargs"],
    )
    corrected.reset_times()
    return corrected


def remove_duplicates(
    sorting: si.BaseSorting,
    recording: si.BaseRecording,
    sparsity: si.ChannelSparsity,
    *,
    duplicate_threshold: float,
    extensions: dict[str, dict],
    return_in_uv: bool,
) -> tuple[si.BaseSorting, si.ChannelSparsity]:
    """The sorting without redundant units, and the sparsity of the units it keeps."""
    analyzer = si.create_sorting_analyzer(
        sorting, recording, sparsity=sparsity, return_in_uV=return_in_uv
    )
    analyzer.compute(
        {"random_spikes": extensions["random_spikes"], "templates": extensions["templates"]}
    )
    deduplicated = cast(
        "si.BaseSorting",
        scur.remove_redundant_units(analyzer, duplicate_threshold=duplicate_threshold),
    )
    unit_indices = sorting.ids_to_indices(deduplicated.unit_ids)
    kept_sparsity = si.ChannelSparsity(
        mask=sparsity.mask[unit_indices, :],
        channel_ids=sparsity.channel_ids,
        unit_ids=deduplicated.unit_ids,
    )
    return deduplicated, kept_sparsity


class AINDEPhysPostprocessingTask(Task):
    """Postprocess every sorted recording into ``postprocessed_<name>.zarr``."""

    name: ClassVar[str] = "AIND Ephys Postprocessing"
    description: ClassVar[str] = "Computes waveforms and quality metrics of sorted units."

    config: AINDEPhysPostprocessingSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,  # ruff: ignore[unused-method-argument]  # ty:ignore[invalid-parameter-default]
        entity_cache: bool = False,  # ruff: ignore[unused-method-argument]
        execution_activity_id: str | None = None,  # ruff: ignore[unused-method-argument]
    ) -> Path:
        output_folder = Path(self.config.coordinate_output_root)
        output_folder.mkdir(parents=True, exist_ok=True)
        sorting_source = Path(self.config.initialize.spikesort_output_path)
        names = stage_output_names(sorting_source, "spikesorted_")
        if not names:
            msg = f"No spikesorted_<name>/ folders in {sorting_source}; sort the recordings first."
            raise FileNotFoundError(msg)
        with global_job_kwargs(self.config.job_kwargs.to_dict()):
            for name in names:
                self.postprocess(name, output_folder)
        return output_folder

    def postprocess(self, name: str, output_folder: Path) -> None:
        """Postprocess one sorted recording."""
        start = datetime.now(UTC)
        init = self.config.initialize
        preprocessing_source = Path(init.preprocessing_output_path)
        sorting_folder = Path(init.spikesort_output_path) / f"spikesorted_{name}"
        analyzer_folder = output_folder / f"postprocessed_{name}.zarr"
        remove_outputs(analyzer_folder)
        if was_skipped(sorting_folder):
            write_skip(analyzer_folder, "Spike sorting skipped this recording")
            return

        recording = load_dumped_recording(preprocessing_source, f"binary_{name}")
        if init.use_motion_corrected:
            recording = motion_corrected(recording, preprocessing_source / f"motion_{name}")
        sorting = load_sorting(sorting_folder)

        extensions = self.config.extensions()
        sparsity = si.estimate_sparsity(
            sorting,
            recording,
            method=self.config.sparsity.method,
            radius_um=self.config.sparsity.radius_um,  # ty:ignore[invalid-argument-type]
        )
        num_units = len(sorting.unit_ids)
        if init.duplicate_threshold is not None:
            sorting, sparsity = remove_duplicates(
                sorting,
                recording,
                sparsity,
                duplicate_threshold=init.duplicate_threshold,
                extensions=extensions,
                return_in_uv=init.return_in_uV,
            )
        num_duplicated = num_units - len(sorting.unit_ids)

        scratch_folder = output_folder / f"scratch_{name}"
        analyzer = si.create_sorting_analyzer(
            sorting,
            recording,
            format="binary_folder",
            folder=scratch_folder,
            overwrite=True,
            sparsity=sparsity,
            return_in_uV=init.return_in_uV,
        )
        analyzer.compute(extensions)
        analyzer.compute("quality_metrics", **self.config.quality_metrics.to_dict())
        analyzer.save_as(format="zarr", folder=analyzer_folder)
        shutil.rmtree(scratch_folder)
        L.info("Postprocessed %s: %d units.", name, len(sorting.unit_ids))

        write_data_process(
            output_folder / f"data_process_postprocessing_{name}.json",
            name="Ephys postprocessing",
            parameters={
                "sparsity": self.config.sparsity.to_dict(),
                "duplicate_threshold": init.duplicate_threshold,
                "extensions": extensions,
                "quality_metrics": self.config.quality_metrics.to_dict(),
            },
            outputs={"duplicated_units": num_duplicated},
            notes=f"- Removed {num_duplicated} duplicated units.\n",
            start=start,
        )

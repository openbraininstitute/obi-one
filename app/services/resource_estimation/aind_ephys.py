"""Disk and time for the AIND ephys tasks, which grow with the size of their input."""

import math
from http import HTTPStatus
from uuid import UUID

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel

from app.errors import ApiError, ApiErrorCode
from app.schemas.task import LaunchableTaskDefinition, Resources, TaskLaunchSubmit
from app.services.resource_estimation.circuit_extraction import (
    EXTRA_DISK_SPACE_LIMIT_GB,
    get_required_extra_storage_space,
)
from app.types import TaskType

DISK_GB_FOR_JOB = 10  # the image and the job's packages
# Preprocessing downloads the NWB file and writes the traces uncompressed, possibly as float32.
PREPROCESSING_DISK_GB_PER_INPUT_GB = 4
# Sorting downloads the preprocessed traces, and the sorter makes a working copy.
SORTING_DISK_GB_PER_INPUT_GB = 2
# Several times what the toy recording took, as the sorters slow down with more channels.
PREPROCESSING_SECONDS_PER_INPUT_GB = 900
SORTING_SECONDS_PER_INPUT_GB = 1800
OVERHEAD_SECONDS = 1800  # cloning the repository, and installing and importing the packages
SECONDS_PER_HOUR = 3600


def _nwb_gb(db_client: entitysdk.Client, recording_id: UUID) -> float:
    recording = db_client.get_entity(
        entity_id=recording_id, entity_type=models.ExtracellularRecording
    )
    asset = db_client.select_assets(recording, selection={"label": AssetLabel.nwb}).one()
    return asset.size / 1e9


def _task_result_gb(db_client: entitysdk.Client, result_id: UUID) -> float:
    result = db_client.get_entity(entity_id=result_id, entity_type=models.TaskResult)
    asset = db_client.select_assets(result, selection={"label": AssetLabel.task_result}).one()
    listing = db_client.list_directory(
        entity_id=result_id, entity_type=models.TaskResult, asset_id=asset.id
    )
    return sum(file.size for file in listing.files.values()) / 1e9


def estimate_task_resources(
    json_model: TaskLaunchSubmit,
    db_client: entitysdk.Client,
    task_definition: LaunchableTaskDefinition,
    compute_cell: str,
) -> Resources:
    """The task definition's resources, with disk and time for the size of the task's input.

    A config without an input sorts the toy recording, which the defaults suit.
    """
    config = db_client.get_entity(entity_id=json_model.config_id, entity_type=models.TaskConfig)
    resources = task_definition.resources.model_copy(update={"compute_cell": compute_cell})
    if not config.inputs:
        return resources

    input_id = config.inputs[0].id
    if task_definition.task_type == TaskType.aind_ephys_preprocessing:
        input_gb = _nwb_gb(db_client, input_id)
        disk_gb_per_input_gb = PREPROCESSING_DISK_GB_PER_INPUT_GB
        seconds_per_input_gb = PREPROCESSING_SECONDS_PER_INPUT_GB
    else:
        input_gb = _task_result_gb(db_client, input_id)
        disk_gb_per_input_gb = SORTING_DISK_GB_PER_INPUT_GB
        seconds_per_input_gb = SORTING_SECONDS_PER_INPUT_GB

    disk_gb = DISK_GB_FOR_JOB + input_gb * disk_gb_per_input_gb
    try:
        storage_gb = get_required_extra_storage_space(disk_gb)
    except ValueError as e:
        msg = (
            f"This input is {input_gb:.0f} GB, so the task needs about {disk_gb:.0f} GB of"
            f" storage, more than the {EXTRA_DISK_SPACE_LIMIT_GB} GB a task can have."
        )
        raise ApiError(
            message=msg,
            error_code=ApiErrorCode.RESOURCE_ESTIMATION_ERROR,
            http_status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        ) from e

    seconds = OVERHEAD_SECONDS + input_gb * seconds_per_input_gb
    hours = math.ceil(seconds / SECONDS_PER_HOUR)
    return resources.model_copy(
        update={"timelimit": f"{hours:02d}:00", "ephemeral_storage": storage_gb}
    )

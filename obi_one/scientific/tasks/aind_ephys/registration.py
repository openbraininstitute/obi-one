"""Registering a pipeline stage's output folder as a TaskResult entity."""

from pathlib import Path
from typing import TYPE_CHECKING

import entitysdk
from entitysdk.models import TaskResult
from entitysdk.types import AssetLabel, TaskResultType

if TYPE_CHECKING:
    from os import PathLike

RESULT_DIRECTORY_NAME = "task_result"


def register_stage_result(
    db_client: entitysdk.client.Client,
    *,
    folder: Path,
    task_result_type: TaskResultType,
    name: str,
    description: str,
    excluded: tuple[str, ...] = (),
) -> TaskResult:
    """Register a TaskResult with ``folder`` as its directory asset.

    ``excluded`` names top-level entries of the folder to leave out, such as a downloaded input.
    """
    result = db_client.register_entity(
        TaskResult(name=name, description=description, task_result_type=task_result_type)
    )
    paths: dict[PathLike, PathLike] = {
        path.relative_to(folder): path
        for path in folder.rglob("*")
        if path.is_file() and path.relative_to(folder).parts[0] not in excluded
    }
    db_client.upload_directory(
        entity_id=result.id,
        entity_type=TaskResult,
        name=RESULT_DIRECTORY_NAME,
        paths=paths,
        label=AssetLabel.task_result,
    )
    return result

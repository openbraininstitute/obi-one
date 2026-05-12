import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import entitysdk

from obi_one.core.deserialize import deserialize_obi_object_from_json_data
from obi_one.core.scan_generation import ScanGenerationTask
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.unions.config_task_map import (
    get_configs_task_type,
    get_task_type,
    get_task_type_config_asset_label,
    get_task_type_single_config,
)
from obi_one.types import TaskType
from obi_one.utils import db_sdk

if TYPE_CHECKING:
    from uuid import UUID


def run_task_for_single_config(
    single_config: SingleConfigMixin,
    *,
    db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    entity_cache: bool = False,
    execution_activity_id: str | None = None,
) -> Any:
    task_type = get_configs_task_type(single_config)
    task = task_type(config=single_config)
    return task.execute(
        db_client=db_client, entity_cache=entity_cache, execution_activity_id=execution_activity_id
    )


def run_task_for_single_configs(
    single_configs: list[SingleConfigMixin],
    *,
    db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    entity_cache: bool = False,
) -> list[Any]:
    return [
        run_task_for_single_config(single_config, db_client=db_client, entity_cache=entity_cache)
        for single_config in single_configs
    ]


def run_tasks_for_generated_scan(
    scan_generation: ScanGenerationTask,
    *,
    db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    entity_cache: bool = False,
) -> Any:
    return run_task_for_single_configs(
        scan_generation.single_configs, db_client=db_client, entity_cache=entity_cache
    )


def run_task_for_single_config_asset(
    entity_type: type[entitysdk.models.entity.Entity],  # ty:ignore[possibly-missing-submodule]
    entity_id: str,
    config_asset_id: str,
    scan_output_root: str,
    *,
    db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    entity_cache: bool = False,
    execution_activity_id: str | None = None,
) -> None:
    """Run the appropriate task for a single configuration stored as an asset."""
    json_str = db_client.download_content(
        entity_id=entity_id,  # ty:ignore[invalid-argument-type]
        entity_type=entity_type,
        asset_id=config_asset_id,  # ty:ignore[invalid-argument-type]
    ).decode(encoding="utf-8")

    json_dict = json.loads(json_str)
    json_dict["scan_output_root"] = scan_output_root
    json_dict["coordinate_output_root"] = Path(scan_output_root) / str(json_dict["idx"])
    single_config = deserialize_obi_object_from_json_data(json_dict)

    entity = db_client.get_entity(entity_id=entity_id, entity_type=entity_type)  # ty:ignore[invalid-argument-type]

    single_config.set_single_entity(entity)  # ty:ignore[unresolved-attribute]
    run_task_for_single_config(
        single_config,  # ty:ignore[invalid-argument-type]
        db_client=db_client,
        entity_cache=entity_cache,
        execution_activity_id=execution_activity_id,
    )


def run_task_type(
    task_type: TaskType,
    entity_type: type[entitysdk.models.entity.Entity],  # ty:ignore[possibly-missing-submodule]
    entity_id: str,
    scan_output_root: str,
    *,
    db_client: entitysdk.client.Client = None,  # ty:ignore[invalid-parameter-default]
    entity_cache: bool = False,
    execution_activity_id: str | None = None,
) -> None:
    entity = db_client.get_entity(entity_id=entity_id, entity_type=entity_type)  # ty:ignore[invalid-argument-type]

    config_asset_label = get_task_type_config_asset_label(task_type)

    if config_asset_label is not None:
        config_asset_id = db_sdk.get_entity_asset_by_label(
            client=db_client,
            config=entity,
            asset_label=config_asset_label,
        ).id
        if config_asset_id is None:
            msg = "Config asset must have an id"
            raise ValueError(msg)

        json_str = db_client.download_content(
            entity_id=entity_id,  # ty:ignore[invalid-argument-type]
            entity_type=entity_type,
            asset_id=cast("UUID", config_asset_id),
        ).decode(encoding="utf-8")

        json_dict = json.loads(json_str)
        json_dict["scan_output_root"] = scan_output_root
        json_dict["coordinate_output_root"] = Path(scan_output_root) / str(json_dict["idx"])
        single_config = deserialize_obi_object_from_json_data(json_dict)

    else:
        single_config = get_task_type_single_config(task_type)(scan_output_root=scan_output_root)

    single_config.set_single_entity(entity)  # ty:ignore[unresolved-attribute]

    task_cls = get_task_type(task_type)
    task = task_cls(config=single_config)
    task.execute(
        db_client=db_client, entity_cache=entity_cache, execution_activity_id=execution_activity_id
    )

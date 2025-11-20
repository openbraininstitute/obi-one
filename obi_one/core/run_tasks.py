import json
from pathlib import Path
from typing import Any

import entitysdk

from obi_one.core.scan_generation import ScanGenerationTask
from obi_one.core.serialization import deserialize_obi_object_from_json_data
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.unions.config_task_map import get_configs_task_type


def run_task_for_single_config(
    single_config: SingleConfigMixin,
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> Any:
    task_type = get_configs_task_type(single_config)
    task = task_type(config=single_config)
    return task.execute(db_client=db_client, entity_cache=entity_cache)


def run_task_for_single_configs(
    single_configs: list[SingleConfigMixin],
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> list[Any]:
    return [
        run_task_for_single_config(single_config, db_client=db_client, entity_cache=entity_cache)
        for single_config in single_configs
    ]


def run_tasks_for_generated_scan(
    scan_generation: ScanGenerationTask,
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> Any:
    return run_task_for_single_configs(
        scan_generation.single_configs, db_client=db_client, entity_cache=entity_cache
    )


def run_task_for_single_config_asset(
    entity_type: type[entitysdk.models.entity.Entity],
    entity_id: str,
    config_asset_id: str,
    scan_output_root: str,
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> None:
    """Run the appropriate task for a single configuration stored as an asset."""
    json_str = db_client.download_content(
        entity_id=entity_id, entity_type=entity_type, asset_id=config_asset_id
    ).decode(encoding="utf-8")

    json_dict = json.loads(json_str)
    json_dict["scan_output_root"] = scan_output_root
    json_dict["coordinate_output_root"] = Path(scan_output_root) / str(json_dict["idx"])
    single_config = deserialize_obi_object_from_json_data(json_dict)

    entity = db_client.get_entity(entity_id=entity_id, entity_type=entity_type)

    single_config.set_single_entity(entity)
    run_task_for_single_config(
        single_config,
        db_client=db_client,
        entity_cache=entity_cache,
    )

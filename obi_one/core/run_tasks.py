import entitysdk

from obi_one.core.scan_generation import ScanGenerationTask
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.unions.config_task_map import get_configs_task_type
from obi_one.core.serialization import deserialize_obi_object_from_json_data


def run_task_for_single_config(
    single_config: SingleConfigMixin,
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> None:
    task_type = get_configs_task_type(single_config)
    task = task_type(config=single_config)
    task.execute(db_client=db_client, entity_cache=entity_cache)


def run_task_for_single_configs(
    single_configs: list[SingleConfigMixin],
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> None:
    for single_config in single_configs:
        run_task_for_single_config(single_config, db_client=db_client, entity_cache=entity_cache)


def run_tasks_for_generated_scan(
    scan_generation: ScanGenerationTask,
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> None:
    run_task_for_single_configs(
        scan_generation.single_configs, db_client=db_client, entity_cache=entity_cache
    )

def run_task_for_single_config_asset(
    entity_type: type[entitysdk.models.entity.Entity],
    entity_id: str,
    config_asset_id: str,
    *,
    db_client: entitysdk.client.Client = None,
    entity_cache: bool = False,
) -> None:
    """
    Run the appropriate task for a single configuration stored as an asset.

    Example usage:
    obi.run_task_for_single_config_asset(entity_type=entitysdk.models.simulation.Simulation, 
                                     entity_id="1569a81e-b578-4c39-a3a9-f9a05f123db9", 
                                     config_asset_id="c9edaedf-e5c0-4643-979c-47375f3160e0", 
                                     db_client=db_client)
    
    """

    content = db_client.download_content(
        entity_id=entity_id,
        entity_type=entity_type,
        asset_id=config_asset_id).decode(encoding="utf-8")
    
    single_config = deserialize_obi_object_from_json_data(content)
    run_task_for_single_config(
        single_config,
        db_client=db_client,
        entity_cache=entity_cache,
    )

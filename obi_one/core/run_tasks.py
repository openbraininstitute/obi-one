import entitysdk

from obi_one.core.scan_generation import ScanGenerationTask
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.unions.config_task_map import get_configs_task_type


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

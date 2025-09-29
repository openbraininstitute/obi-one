from pathlib import Path

import entitysdk

from obi_one.core.base import OBIBaseModel
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.tasks.scan_generation import ScanGenerationTask
from obi_one.scientific.unions.unions_scan_configs import ScanConfigsUnion
from obi_one.scientific.unions.unions_tasks import get_configs_task_type


def run_task_for_single_config(
    single_config: SingleConfigMixin, db_client: entitysdk.client.Client = None
) -> None:
    task_type = get_configs_task_type(single_config)
    task = task_type(config=single_config)
    task.execute(db_client=db_client)


def run_task_for_single_configs(
    single_configs: list[SingleConfigMixin], db_client: entitysdk.client.Client = None
) -> None:
    for single_config in single_configs:
        run_task_for_single_config(single_config, db_client=db_client)


def run_task_for_single_configs_of_generated_scan(
    scan_generation: ScanGenerationTask, db_client: entitysdk.client.Client = None
) -> None:
    run_task_for_single_configs(scan_generation.single_configs, db_client=db_client)


class ScanWrapper(OBIBaseModel):
    scan_config: ScanConfigsUnion
    scan_generation_type: type[ScanGenerationTask]
    output_root: Path = Path()
    coordinate_directory_option: str = "NAME_EQUALS_VALUE"

    def generate_scan(self) -> None:
        scan_generation_task = self.scan_generation_type(
            form=self.scan_config,
            output_root=self.output_root,
            coordinate_directory_option=self.coordinate_directory_option,
        )

        scan_generation_task.execute()
        run_task_for_single_configs_of_generated_scan(self.scan_generation_task)

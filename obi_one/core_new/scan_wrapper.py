from pathlib import Path

from obi_one.core.base import OBIBaseModel
from obi_one.core_new.single_config_mixin import SingleConfigMixin
from obi_one.scientific.tasks.scan_generation import ScanGeneration
from obi_one.scientific.unions.unions_scan_configs import ScanConfigsUnion
from obi_one.scientific.unions.unions_tasks import get_configs_task_type


def run_task_for_single_config(single_config: SingleConfigMixin) -> None:
    task_type = get_configs_task_type(single_config)
    task = task_type(config=single_config)
    task.execute()


def run_task_for_single_configs(single_configs: list[SingleConfigMixin]) -> None:
    for single_config in single_configs:
        run_task_for_single_config(single_config)


def run_task_for_single_configs_of_generated_scan(scan_generation: ScanGeneration) -> None:
    run_task_for_single_configs(scan_generation.single_configs)


class ScanWrapper(OBIBaseModel):
    scan_config: ScanConfigsUnion
    scan_generation_type: type[ScanGeneration]
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

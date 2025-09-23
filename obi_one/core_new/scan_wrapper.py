from pathlib import Path

from obi_one.core.base import OBIBaseModel
from obi_one.core_new.task import Task
from obi_one.scientific.tasks.scan_generation import ScanGeneration
from obi_one.scientific.unions.unions_scan_configs import ScanConfigsUnion
from obi_one.scientific.unions.unions_tasks import get_task_config_type


class ScanWrapper(OBIBaseModel):
    scan_config: ScanConfigsUnion
    scan_generation_type: type[ScanGeneration]
    output_root: Path = Path()
    coordinate_directory_option: str = "NAME_EQUALS_VALUE"

    def generate_scan(self) -> None:
        scan_generation = self.scan_generation_type(
            scan_config=self.scan_config,
            output_root=self.output_root,
            coordinate_directory_option=self.coordinate_directory_option,
        )
        single_configs, _ = scan_generation.execute()

        task_type = get_task_config_type(single_configs[0])

        for single_config in single_configs:
            task = task_type(single_config=single_config)
            task.execute()

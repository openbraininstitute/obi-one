from pathlib import Path

from obi_one.core.base import OBIBaseModel
from obi_one.core_new.task import Task
from obi_one.scientific.tasks.scan_generation import ScanGeneration
from obi_one.scientific.unions.union_scan_configs import ScanConfigsUnion


class ScanWrapper(OBIBaseModel):
    scan_config: ScanConfigsUnion
    scan_generation_type: type[ScanGeneration]
    task_type: type[Task]
    output_root: Path = Path()
    coordinate_directory_option: str = "NAME_EQUALS_VALUE"

    def generate_scan(self) -> None:
        scan_generation = self.scan_generation_type(
            scan_config=self.scan_config,
            output_root=self.output_root,
            coordinate_directory_option=self.coordinate_directory_option,
        )
        single_configs, _ = scan_generation.execute()

        for single_config in single_configs:
            task = self.task_type(single_config=single_config)
            task.execute()

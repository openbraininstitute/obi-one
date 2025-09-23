from typing import ClassVar

import entitysdk

from obi_one.core.block import Block
from obi_one.core.path import NamedPath
from obi_one.core_new.scan_config import ScanConfig
from obi_one.core_new.single_config_mixin import SingleConfigMixin
from obi_one.core_new.task import Task


class ExampleScanConfig(ScanConfig):
    single_coord_class_name: ClassVar[str] = (
        "ExampleSingleConfig"  # Change to single_config_class_name
    )
    name: ClassVar[str] = "Title for UI + AI Agent"
    description: ClassVar[str] = "Title for UI + AI Agent"

    class Initialize(Block):
        morphology_path: NamedPath | list[NamedPath]
        param_a: int

    initialize: Initialize


class ExampleSingleConfig(ExampleScanConfig, SingleConfigMixin):
    pass


class ExampleTask(Task):
    config: ExampleSingleConfig

    def execute(self, db_client: entitysdk.client.Client = None) -> tuple[str, None]:
        # Arbitrary operation
        x = str(self.config.initialize.morphology_path) + str(
            self.config.initialize.param_a
        )

        if db_client:
            # Do an entitycore operation
            pass

        return x, None

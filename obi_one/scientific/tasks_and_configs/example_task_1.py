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


import entitysdk


class ExampleTask(Task):
    single_config: ExampleSingleConfig

    def execute(self, db_client: entitysdk.client.Client = None):
        # Arbitrary operation
        x = str(self.single_config.initialize.morphology_path) + str(
            self.single_config.initialize.param_a
        )

        if db_client:
            # Do an entitycore operation
            pass

        return x, None

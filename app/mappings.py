from pathlib import Path

from entitysdk import models
from entitysdk.types import AssetLabel
from obp_accounting_sdk.constants import ServiceSubtype

from app.config import settings
from app.schemas.task import (
    BuiltinCode,
    ClusterResources,
    MachineResources,
    PythonRepositoryCode,
    TaskDefinition,
)
from app.types import BuiltinScript, TaskType

OBI_ONE_CODE_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "code.py")
OBI_ONE_DEPS_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "requirements.txt")


TASK_DEFINITIONS: dict[TaskType, TaskDefinition] = {
    TaskType.circuit_extraction: TaskDefinition(
        task_type=TaskType.circuit_extraction,
        config_type=models.CircuitExtractionConfig,
        activity_type=models.CircuitExtractionExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_CIRCUIT_SIM,
        config_asset_label=AssetLabel.circuit_extraction_config,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref="tag:2026.1.7",
            path=OBI_ONE_CODE_PATH,
            dependencies=OBI_ONE_DEPS_PATH,
        ),
        resources=MachineResources(
            cores=1,
            memory=2,
            timelimit="00:10",
        ),
    ),
    TaskType.circuit_simulation: TaskDefinition(
        task_type=TaskType.circuit_simulation,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_SIM,  # May be overridden by circuit scale
        config_asset_label=AssetLabel.sonata_simulation_config,
        code=BuiltinCode(
            script=BuiltinScript.circuit_simulation,
        ),
        resources=ClusterResources(
            instances=1,
            instance_type="small",
            timelimit="00:10",
        ),
    ),
}

from pathlib import Path

from entitysdk import models
from entitysdk.types import AssetLabel
from obp_accounting_sdk.constants import ServiceSubtype

from app.config import settings
from app.schemas.task import (
    BuiltinCode,
    Capabilities,
    ClusterResources,
    MachineResources,
    PythonRepositoryCode,
    TaskDefinition,
)
from app.types import BuiltinScript, TaskType
from obi_one.scientific.unions.config_task_map import (
    get_task_type_config_asset_label,
)

APP_TAG = f"tag:{settings.APP_VERSION.split('-')[0]}"
OBI_ONE_CODE_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "code.py")
OBI_ONE_DEPS_DIR = Path(settings.OBI_ONE_LAUNCH_PATH) / "dependencies"


TASK_DEFINITIONS: dict[TaskType, TaskDefinition] = {
    TaskType.circuit_extraction: TaskDefinition(
        task_type=TaskType.circuit_extraction,
        config_type=models.CircuitExtractionConfig,
        activity_type=models.CircuitExtractionExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_CIRCUIT_SIM,
        config_asset_label=get_task_type_config_asset_label(TaskType.circuit_extraction),
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=2,
            timelimit="00:10",
            compute_cell="local",
        ),
    ),
    TaskType.morphology_skeletonization: TaskDefinition(
        task_type=TaskType.morphology_skeletonization,
        config_type=models.SkeletonizationConfig,
        activity_type=models.SkeletonizationExecution,
        accounting_service_subtype=ServiceSubtype.NEURON_MESH_SKELETONIZATION,
        config_asset_label=get_task_type_config_asset_label(TaskType.morphology_skeletonization),
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "skeletonization.txt"),
            capabilities=Capabilities(private_packages=True),
        ),
        resources=MachineResources(
            cores=16,
            memory=32,
            timelimit="00:30",
            compute_cell="local",
        ),
    ),
    TaskType.circuit_simulation: TaskDefinition(
        task_type=TaskType.circuit_simulation,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_SIM,  # May be overridden by circuit scale
        config_asset_label=get_task_type_config_asset_label(TaskType.circuit_simulation),
        code=BuiltinCode(
            script=BuiltinScript.circuit_simulation,
        ),
        resources=ClusterResources(
            instances=1,
            instance_type="small",
            timelimit="00:10",
            compute_cell="local",
        ),
    ),
    TaskType.ion_channel_model_simulation_execution: TaskDefinition(
        task_type=TaskType.ion_channel_model_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_SIM,
        config_asset_label=get_task_type_config_asset_label(TaskType.ion_channel_model_simulation_execution),
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref="commit:f0e3a06f869af212ab7392a39ba1a0a536f0e03f",
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=2,
            timelimit="00:10",
            compute_cell="local",
        ),
    ),
}

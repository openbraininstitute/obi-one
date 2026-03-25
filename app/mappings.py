from pathlib import Path

from entitysdk import models
from entitysdk.types import TaskActivityType, TaskConfigType
from obp_accounting_sdk.constants import ServiceSubtype

from app.config import settings
from app.schemas.task import (
    BuiltinCode,
    Capabilities,
    ClusterResources,
    MachineResources,
    PythonRepositoryCode,
    TaskDefinition,
    TaskDefinitionLegacy,
)
from app.types import BuiltinScript, TaskType

APP_TAG = f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}"
OBI_ONE_CODE_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "code.py")
OBI_ONE_DEPS_DIR = Path(settings.OBI_ONE_LAUNCH_PATH) / "dependencies"


TASK_DEFINITIONS: dict[TaskType, TaskDefinition] = {
    TaskType.circuit_extraction: TaskDefinition(
        task_type=TaskType.circuit_extraction,
        config_type=TaskConfigType.circuit_extraction__config,
        activity_type=TaskActivityType.circuit_extraction__execution,
        accounting_service_subtype=ServiceSubtype.SMALL_CIRCUIT_SIM,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "circuit_extraction.txt"),
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
        config_type=TaskConfigType.skeletonization__config,
        activity_type=TaskActivityType.skeletonization__execution,
        accounting_service_subtype=ServiceSubtype.NEURON_MESH_SKELETONIZATION,
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
    TaskType.circuit_simulation: TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_SIM,  # May be overridden by circuit scale
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
    TaskType.ion_channel_model_simulation_execution: TaskDefinitionLegacy(
        task_type=TaskType.ion_channel_model_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        accounting_service_subtype=ServiceSubtype.SMALL_SIM,
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
    TaskType.em_synapse_mapping: TaskDefinition(
        task_type=TaskType.em_synapse_mapping,
        config_type=TaskConfigType.em_synapse_mapping__config,
        activity_type=TaskActivityType.em_synapse_mapping__execution,
        accounting_service_subtype=ServiceSubtype.SMALL_CIRCUIT_SIM,
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
}

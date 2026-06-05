from pathlib import Path

from entitysdk import models
from entitysdk.types import TaskActivityType, TaskConfigType

from app.config import settings
from app.schemas.cluster import ClusterInstanceInfo
from app.schemas.task import (
    BuiltinCode,
    Capabilities,
    ClusterResources,
    MachineResources,
    PythonRepositoryCode,
    TaskDefinition,
    TaskDefinitionLegacy,
    TaskGroupLegacyDefinition,
)
from app.types import BuiltinScript, MachineExecutorImageType, TaskType
from obi_one.config import settings as obi_settings

# APP_TAG = f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}"  # noqa: ERA001
APP_TAG = "commit:ab9963566cecf3b823a0056ef90861f7da5a109e"
OBI_ONE_CODE_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "main.py")
OBI_ONE_DEPS_DIR = Path(settings.OBI_ONE_LAUNCH_PATH) / "dependencies"


TASK_DEFINITIONS: dict[TaskType, TaskDefinition] = {
    TaskType.circuit_extraction: TaskDefinition(
        task_type=TaskType.circuit_extraction,
        config_type=TaskConfigType.circuit_extraction__config,
        activity_type=TaskActivityType.circuit_extraction__execution,
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
            timelimit="02:00",
            compute_cell="local",
        ),
    ),
    TaskType.circuit_simulation: TaskGroupLegacyDefinition(
        task_type=TaskType.circuit_simulation,
        config_type=models.Simulation,
    ),
    TaskType.circuit_simulation_inait_machine: TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_inait_machine,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location="https://github.com/openbraininstitute-partners/inait",
            ref="commit:55428c970249d37d4d0f22f69a81ab07987dfa33",
            path="scripts/simulate-circuits/run.py",
            dependencies="scripts/simulate-circuits/requirements.txt",
            staged_directories=["wheels", "scripts/simulate-circuits/"],
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="02:00",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_inait,
        ),
    ),
    TaskType.circuit_simulation_brian2_machine: TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_brian2_machine,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path="obi_one/scientific/library/simulation/brian2/simulate_brian2.py",
            dependencies="obi_one/scientific/library/simulation/brian2/requirements.txt",
            staged_directories=[],
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="02:00",
            compute_cell="local",
        ),
    ),
    TaskType.circuit_simulation_neuron: TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_neuron,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="00:10",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskType.circuit_simulation_neurodamus_cluster: TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_neurodamus_cluster,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=BuiltinCode(
            script=BuiltinScript.circuit_simulation,
        ),
        resources=ClusterResources(
            instances=1,
            instance_type="small",
            timelimit=None,
            compute_cell="local",
        ),
    ),
    TaskType.ion_channel_model_simulation_execution: TaskDefinitionLegacy(
        task_type=TaskType.ion_channel_model_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
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
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskType.em_synapse_mapping: TaskDefinition(
        task_type=TaskType.em_synapse_mapping,
        config_type=TaskConfigType.em_synapse_mapping__config,
        activity_type=TaskActivityType.em_synapse_mapping__execution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
            capabilities=Capabilities(
                env_secrets=[obi_settings.cave_client_config.microns_api_key]
            ),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="00:30",
            compute_cell="local",
        ),
    ),
    TaskType.extracellular_recording_weights_calculation: TaskDefinition(
        task_type=TaskType.extracellular_recording_weights_calculation,
        config_type=TaskConfigType.extracellular_recording_weights_calculation__config,
        activity_type=TaskActivityType.extracellular_recording_weights_calculation__execution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "extracellular_recording_weights_calculation.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="02:00",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
}  # ty:ignore[invalid-assignment]

CLUSTER_INSTANCES_INFO = {
    "cell_a": [
        ClusterInstanceInfo(
            name="small",
            max_neurons=100,
            memory_per_instance_gb=16,
        ),
        ClusterInstanceInfo(
            name="large",
            max_neurons=1_000_000,
            memory_per_instance_gb=768,
        ),
    ],
    "cell_b": [
        ClusterInstanceInfo(
            name="small",
            max_neurons=100,
            memory_per_instance_gb=8,
        ),
        ClusterInstanceInfo(
            name="large",
            max_neurons=1_000_000,
            memory_per_instance_gb=788,
        ),
    ],
}

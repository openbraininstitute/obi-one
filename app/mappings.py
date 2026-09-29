from collections.abc import Iterable, Mapping
from pathlib import Path

from entitysdk import models
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import TypeAdapter

from app.config import settings
from app.schemas.cluster import ClusterInstanceInfo
from app.schemas.task import (
    AnyTaskDefinition,
    BuiltinCode,
    Capabilities,
    ClusterResources,
    LaunchableTaskDefinition,
    MachineResources,
    PythonRepositoryCode,
    TaskDefinition,
    TaskDefinitionLegacy,
    TaskGroupLegacyDefinition,
)
from app.types import BuiltinScript, MachineExecutorImageType, MachinePlacementType, TaskType
from obi_one.config import settings as obi_settings
from obi_one.utils.versions import ReleaseVersion, launch_ref

OBI_ONE_CODE_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "main.py")
OBI_ONE_DEPS_DIR = Path(settings.OBI_ONE_LAUNCH_PATH) / "dependencies"

# Keeps a task on an obi-one release (e.g. "2026.9.15") instead of the service version: the
# task checks out ``tag:launch-<version>``, so its code, requirements and obi-one wheel all come
# from that release. Only tasks running code from the obi-one repository can be pinned.
PINNED_OBI_ONE_VERSIONS: dict[TaskType, str] = TypeAdapter(
    dict[TaskType, ReleaseVersion]
).validate_python({})


def _obi_one_code(
    deps_name: str,
    *,
    capabilities: Capabilities | None = None,
) -> PythonRepositoryCode:
    """Standard obi-one launch code: the obi-one repo at the service's launch ref, running main.py.

    Legacy tasks with a different repo/entrypoint build ``PythonRepositoryCode`` directly.
    """
    return PythonRepositoryCode(
        location=settings.OBI_ONE_REPO,
        ref=launch_ref(settings.APP_VERSION),
        path=OBI_ONE_CODE_PATH,
        dependencies=str(OBI_ONE_DEPS_DIR / deps_name),
        capabilities=capabilities or Capabilities(),
    )


def _build_task_definitions(
    definitions: Iterable[AnyTaskDefinition],
    pins: Mapping[TaskType, str],
) -> dict[TaskType, AnyTaskDefinition]:
    """Index ``definitions`` by their own ``task_type`` and apply obi-one version pins.

    Keying by ``task_type`` means each task type is written once per definition. A pinned
    task keeps its code but checks out the launch ref of the pinned version.
    """
    result: dict[TaskType, AnyTaskDefinition] = {}
    for definition in definitions:
        if definition.task_type in result:
            msg = f"Duplicate task definition for {definition.task_type!r}"
            raise ValueError(msg)
        result[definition.task_type] = definition

    for task_type, version in pins.items():
        code = getattr(result.get(task_type), "code", None)
        if not isinstance(code, PythonRepositoryCode) or code.location != settings.OBI_ONE_REPO:
            msg = f"Cannot pin obi-one version for {task_type!r}: not obi-one repository code"
            raise ValueError(msg)
        pinned_code = code.model_copy(update={"ref": launch_ref(version)})
        result[task_type] = result[task_type].model_copy(update={"code": pinned_code})
    return result


_TASK_DEFINITIONS: list[AnyTaskDefinition] = [
    TaskDefinition(
        task_type=TaskType.circuit_extraction,
        config_type=TaskConfigType.circuit_extraction__config,
        activity_type=TaskActivityType.circuit_extraction__execution,
        code=_obi_one_code("circuit_extraction.txt"),
        resources=MachineResources(
            cores=1,
            memory=2,
            timelimit="00:10",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
        ),
    ),
    TaskDefinition(
        task_type=TaskType.circuit_single_build,
        config_type=TaskConfigType.circuit_single_build__config,
        activity_type=TaskActivityType.circuit_single_build__execution,
        code=_obi_one_code("default.txt"),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="00:30",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
        ),
    ),
    TaskGroupLegacyDefinition(
        task_type=TaskType.circuit_simulation,
        config_type=models.Simulation,
    ),
    TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_inait_machine,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location="https://github.com/openbraininstitute-partners/inait",
            ref="commit:62a6257b91872483ee6ffd6d5f61ba8642ffe67f",
            path="scripts/simulate-circuits/run.py",
            dependencies="scripts/simulate-circuits/requirements.txt",
            staged_directories=["wheels", "scripts/simulate-circuits/"],
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="02:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
            image_type=MachineExecutorImageType.python_3_12_inait,
        ),
    ),
    TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_brian2_machine,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=launch_ref(settings.APP_VERSION),
            path="obi_one/scientific/library/simulation/brian2/simulate_brian2.py",
            dependencies="launch_scripts/launch_brian2_simulation/dependencies/default.txt",
            staged_directories=[],
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="02:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
        ),
    ),
    TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_neuron,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=_obi_one_code("default.txt"),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="00:10",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_neurodamus_machine,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=_obi_one_code("default.txt"),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskDefinitionLegacy(
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
    TaskDefinitionLegacy(
        task_type=TaskType.ion_channel_model_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=_obi_one_code("default.txt"),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.ecs_managed_instances,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskDefinitionLegacy(
        task_type=TaskType.single_neuron_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=_obi_one_code("default.txt"),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.ecs_managed_instances,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskDefinitionLegacy(
        task_type=TaskType.single_neuron_synaptome_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=_obi_one_code("default.txt"),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.ecs_managed_instances,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskDefinition(
        task_type=TaskType.circuit_synaptic_physiology_assignment,
        config_type=TaskConfigType.circuit_synaptic_physiology_assignment__config,
        activity_type=TaskActivityType.circuit_synaptic_physiology_assignment__execution,
        code=_obi_one_code("synapse_parameterization.txt"),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
        ),
    ),
    TaskDefinition(
        task_type=TaskType.em_synapse_mapping,
        config_type=TaskConfigType.em_synapse_mapping__config,
        activity_type=TaskActivityType.em_synapse_mapping__execution,
        code=_obi_one_code(
            "default.txt",
            capabilities=Capabilities(
                env_secrets=[obi_settings.cave_client_config.microns_api_key]
            ),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="00:30",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
        ),
    ),
    TaskDefinition(
        task_type=TaskType.efeature_extraction,
        config_type=TaskConfigType.efeature_extraction__config,
        activity_type=TaskActivityType.efeature_extraction__execution,
        code=_obi_one_code("emodel_building.txt"),
        resources=MachineResources(
            cores=1,
            memory=4,
            timelimit="00:30",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
        ),
    ),
    TaskDefinition(
        task_type=TaskType.emodel_optimization,
        config_type=TaskConfigType.emodel_optimization__config,
        activity_type=TaskActivityType.emodel_optimization__execution,
        code=BuiltinCode(script=BuiltinScript.emodel_optimisation),
        resources=ClusterResources(
            instances=1,
            instance_type="large",
            timelimit="02:00",
            compute_cell="cell_a",
        ),
    ),
    TaskDefinition(
        task_type=TaskType.extracellular_recording_weights_calculation,
        config_type=TaskConfigType.extracellular_recording_weights_calculation__config,
        activity_type=TaskActivityType.extracellular_recording_weights_calculation__execution,
        code=_obi_one_code("extracellular_recording_weights_calculation.txt"),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="02:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskDefinition(
        task_type=TaskType.morphology_skeletonization,
        config_type=TaskConfigType.skeletonization__config,
        activity_type=TaskActivityType.skeletonization__execution,
        code=_obi_one_code("skeletonization.txt", capabilities=Capabilities(private_packages=True)),
        resources=MachineResources(
            cores=16,
            memory=32,
            timelimit="02:00",
            compute_cell="local",
            placement_type_map={
                "cell_a": MachinePlacementType.fargate,
                "cell_b": MachinePlacementType.azure_container_apps,
            },
        ),
    ),
]

TASK_DEFINITIONS: dict[TaskType, AnyTaskDefinition] = _build_task_definitions(
    definitions=_TASK_DEFINITIONS, pins=PINNED_OBI_ONE_VERSIONS
)


def get_launchable_task_definition(task_type: TaskType) -> LaunchableTaskDefinition:
    """Return a launchable task definition (with code and resources).

    ``TaskGroupLegacyDefinition`` entries are selectors only and must be resolved to a concrete
    task type before calling this.
    """
    task_definition = TASK_DEFINITIONS[task_type]
    if isinstance(task_definition, TaskGroupLegacyDefinition):
        msg = f"Task type '{task_type}' is a task group, not a launchable task"
        raise TypeError(msg)
    return task_definition


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

from pathlib import Path

from entitysdk import models
from entitysdk.types import TaskActivityType, TaskConfigType

from app.config import settings
from app.dependencies.constraints import build_obi_one_constraint_from_file
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

APP_TAG = f"tag:{(settings.APP_VERSION or '0.0.0').split('-')[0]}"
OBI_ONE_CODE_PATH = str(Path(settings.OBI_ONE_LAUNCH_PATH) / "main.py")
OBI_ONE_DEPS_DIR = Path(settings.OBI_ONE_LAUNCH_PATH) / "dependencies"

# Per-task obi-one version pin (calver, e.g. "2026.5.1"). Tasks listed here are
# checked out and installed at the pinned obi-one version instead of the running
# service version -- use this to keep a task on an older, known-good obi-one when
# it has not been validated against the current release. Both the git ``ref``
# (task code + frozen requirements) and the obi-one dependency constraint are
# pinned together so the task runs fully at that version.
_PINNED_OBI_ONE_VERSIONS: dict[TaskType, str] = {}


def _obi_one_deps_constraint(deps_name: str, version: str | None = None) -> list[str]:
    """Build the dynamic obi-one constraint for a launch-script deps file.

    Pins ``obi-one`` to ``version`` when given, otherwise to the running service
    version. Extras are read from the requirements file so they stay in sync.
    Returns an empty list when the version is a dev/unreleased build.
    """
    app_version = version if version is not None else settings.APP_VERSION
    return build_obi_one_constraint_from_file(app_version, OBI_ONE_DEPS_DIR / deps_name)


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
            dependency_constraints=_obi_one_deps_constraint("circuit_extraction.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=2,
            timelimit="00:10",
            compute_cell="local",
        ),
    ),
    TaskType.circuit_single_build: TaskDefinition(
        task_type=TaskType.circuit_single_build,
        config_type=TaskConfigType.circuit_single_build__config,
        activity_type=TaskActivityType.circuit_single_build__execution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="00:30",
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
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="00:10",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskType.circuit_simulation_neurodamus_machine: TaskDefinitionLegacy(
        task_type=TaskType.circuit_simulation_neurodamus_machine,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
        ),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
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
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
        ),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskType.single_neuron_simulation_execution: TaskDefinitionLegacy(
        task_type=TaskType.single_neuron_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
        ),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskType.single_neuron_synaptome_simulation_execution: TaskDefinitionLegacy(
        task_type=TaskType.single_neuron_synaptome_simulation_execution,
        config_type=models.Simulation,
        activity_type=models.SimulationExecution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
        ),
        resources=MachineResources(
            cores=4,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
        ),
    ),
    TaskType.circuit_synaptic_physiology_assignment: TaskDefinition(
        task_type=TaskType.circuit_synaptic_physiology_assignment,
        config_type=TaskConfigType.circuit_synaptic_physiology_assignment__config,
        activity_type=TaskActivityType.circuit_synaptic_physiology_assignment__execution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "default.txt"),
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="01:00",
            compute_cell="local",
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
            dependency_constraints=_obi_one_deps_constraint("default.txt"),
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
    TaskType.efeature_extraction: TaskDefinition(
        task_type=TaskType.efeature_extraction,
        config_type=TaskConfigType.efeature_extraction__config,
        activity_type=TaskActivityType.efeature_extraction__execution,
        code=PythonRepositoryCode(
            location=settings.OBI_ONE_REPO,
            ref=APP_TAG,
            path=OBI_ONE_CODE_PATH,
            dependencies=str(OBI_ONE_DEPS_DIR / "emodel_building.txt"),
            dependency_constraints=_obi_one_deps_constraint("emodel_building.txt"),
        ),
        resources=MachineResources(
            cores=1,
            memory=4,
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
            dependency_constraints=_obi_one_deps_constraint(
                "extracellular_recording_weights_calculation.txt"
            ),
        ),
        resources=MachineResources(
            cores=1,
            memory=8,
            timelimit="02:00",
            compute_cell="local",
            image_type=MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus,
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
            dependency_constraints=_obi_one_deps_constraint("skeletonization.txt"),
            capabilities=Capabilities(private_packages=True),
        ),
        resources=MachineResources(
            cores=16,
            memory=32,
            timelimit="02:00",
            compute_cell="local",
        ),
    ),
}  # ty:ignore[invalid-assignment]


def _apply_obi_one_version_pins() -> None:
    """Pin selected tasks to a specific obi-one version (ref + constraint).

    For each task in ``_PINNED_OBI_ONE_VERSIONS`` the git ``ref`` is set to
    ``tag:<version>`` (so the task code and frozen requirements are checked out
    at that release) and the obi-one dependency constraint is pinned to the same
    version, keeping the code and the installed library consistent.
    """
    for task_type, version in _PINNED_OBI_ONE_VERSIONS.items():
        task_def = TASK_DEFINITIONS.get(task_type)
        code = getattr(task_def, "code", None)
        if task_def is None or not isinstance(code, PythonRepositoryCode):
            msg = f"Cannot pin obi-one version for unknown/non-repository task {task_type!r}"
            raise RuntimeError(msg)
        deps_name = Path(code.dependencies).name
        pinned_code = code.model_copy(
            update={
                "ref": f"tag:{version}",
                "dependency_constraints": _obi_one_deps_constraint(deps_name, version=version),
            }
        )
        TASK_DEFINITIONS[task_type] = task_def.model_copy(update={"code": pinned_code})


_apply_obi_one_version_pins()

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

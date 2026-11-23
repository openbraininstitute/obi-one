from pathlib import Path

from app import mappings
from app.mappings import get_launchable_task_definition
from app.schemas.task import MachineResources, PythonRepositoryCode
from app.types import MachineExecutorImageType, TaskType

_NEURODAMUS_IMAGE_TASKS = (
    TaskType.circuit_simulation_neuron,
    TaskType.circuit_simulation_neurodamus_machine,
    TaskType.ion_channel_fitting,
    TaskType.ion_channel_model_simulation_execution,
    TaskType.memodel_build,
    TaskType.single_neuron_simulation_execution,
    TaskType.single_neuron_synaptome_simulation_execution,
    TaskType.extracellular_recording_weights_calculation,
)


def test_neurodamus_image_tasks_share_deps_and_image_type():
    expected_deps = str(Path(mappings.OBI_ONE_DEPS_DIR) / "neurodamus_image.txt")
    for task_type in _NEURODAMUS_IMAGE_TASKS:
        definition = get_launchable_task_definition(task_type)
        assert isinstance(definition.code, PythonRepositoryCode)
        assert isinstance(definition.resources, MachineResources)
        assert definition.code.dependencies == expected_deps
        assert (
            definition.resources.image_type
            == MachineExecutorImageType.python_3_12_openmpi5_neuron9_neurodamus
        )


def test_neurodamus_image_includes_builder_and_bluecellulab():
    in_file = Path(mappings.__file__).resolve().parents[1] / Path(
        "launch_scripts/launch_task_for_single_config_asset/dependencies/neurodamus_image.in"
    )
    text = in_file.read_text()
    assert "ion-channel-builder" in text
    assert "bluecellulab" in text

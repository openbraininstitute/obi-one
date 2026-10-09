from unittest.mock import MagicMock, patch

import pytest
from entitysdk.types import AssetLabel

from obi_one.core import run_tasks
from obi_one.core.base import OBIBaseModel
from obi_one.core.task import Task
from obi_one.scientific.mappings_and_registry import config_task_map as test_module
from obi_one.scientific.mappings_and_registry.config_task_map import TASK_SPECS
from obi_one.scientific.tasks.build_synaptome import (
    MEModelSynapticModelPlacementSingleConfig,
    MEModelSynapticModelPlacementTask,
)
from obi_one.scientific.tasks.circuit_extraction import (
    CircuitExtractionScanConfig,
    CircuitExtractionSingleConfig,
    CircuitExtractionTask,
)
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingScanConfig
from obi_one.scientific.tasks.generate_simulations.config.neuron.aliases import Simulation
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_ion_channel_models import (
    IonChannelModelSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.task.task import GenerateSimulationTask
from obi_one.scientific.tasks.simulation_execution import (
    CircuitSimulationExecutionSingleConfig,
    CircuitSimulationExecutionTask,
    IonChannelModelSimulationExecutionSingleConfig,
    IonChannelModelSimulationExecutionTask,
    SingleNeuronSimulationExecutionSingleConfig,
    SingleNeuronSimulationExecutionTask,
    SingleNeuronSynaptomeSimulationExecutionSingleConfig,
    SingleNeuronSynaptomeSimulationExecutionTask,
)
from obi_one.scientific.tasks.skeletonization import (
    SkeletonizationScanConfig,
    SkeletonizationSingleConfig,
    SkeletonizationTask,
)
from obi_one.types import TaskType
from obi_one.utils.lazy_import import class_name, import_class

# Task types registered in ``TASK_SPECS``, derived so the list cannot drift from the registry.
CONFIG_TASK_MAP_CASES = tuple(TASK_SPECS)

# Launch-system task types that are not registered in ``config_task_map``.
LAUNCH_SYSTEM_TASK_TYPES_WITHOUT_CONFIG_MAP = (
    TaskType.circuit_simulation_inait_machine,
    TaskType.circuit_simulation_neuron,
    TaskType.circuit_simulation_neurodamus_cluster,
    TaskType.circuit_simulation_brian2_machine,
)

# Every class reference declared by any task spec, with the field it came from for the test id.
CLASS_REF_FIELDS = ("task_ref", "single_config_ref", "scan_config_ref")
DECLARED_CLASS_REFS = tuple(
    (task_type, field, getattr(task_spec, field))
    for task_type, task_spec in TASK_SPECS.items()
    for field in CLASS_REF_FIELDS
    if getattr(task_spec, field) is not None
)


def skip_if_unavailable(task_type: TaskType) -> None:
    """Skip a case whose task needs an optional dependency that is not installed."""
    if not test_module._is_task_type_available(task_type):
        pytest.skip(f"{task_type!r} requires an optional dependency that is not installed")


def test_config_task_map_cases_partition_task_type_enum():
    mapped = set(CONFIG_TASK_MAP_CASES)
    unmapped = set(LAUNCH_SYSTEM_TASK_TYPES_WITHOUT_CONFIG_MAP)
    assert mapped.isdisjoint(unmapped)
    assert mapped | unmapped == set(TaskType)


@pytest.mark.parametrize(
    ("task_type", "class_ref"),
    [(task_type, ref) for task_type, _, ref in DECLARED_CLASS_REFS],
    ids=[f"{task_type.value}-{field}" for task_type, field, _ in DECLARED_CLASS_REFS],
)
def test_declared_class_ref_is_importable(task_type, class_ref):
    """Every reference in ``TASK_SPECS`` must import and name the class it claims.

    This replaces the compile-time safety of the inline ``from … import …`` statements the
    declarative registry got rid of: it catches typos, moved modules and renamed classes.
    """
    skip_if_unavailable(task_type)

    cls = import_class(class_ref)

    assert isinstance(cls, type), f"{class_ref} is not a class"
    assert cls.__qualname__ == class_name(class_ref), (
        f"{class_ref} resolves to {cls.__qualname__!r}, not {class_name(class_ref)!r}"
    )


def test_import_class_caches_resolved_classes():
    class_ref = TASK_SPECS[TaskType.circuit_extraction].task_ref

    assert import_class(class_ref) is import_class(class_ref)


@pytest.mark.parametrize("task_type", CONFIG_TASK_MAP_CASES)
def test_config_task_map_spec_resolves(task_type: TaskType):
    skip_if_unavailable(task_type)
    task_spec = test_module.get_task_spec_for_task_type(task_type)

    assert issubclass(task_spec.task_cls, Task)
    assert issubclass(task_spec.single_config_cls, OBIBaseModel)
    assert test_module.get_task_spec_for_single_config(task_spec.single_config_cls) is task_spec

    if task_spec.scan_config_cls is not None:
        assert test_module.get_task_spec_for_scan_config(task_spec.scan_config_cls) is task_spec


def test_config_name_indexes_cover_every_spec():
    """The reverse indexes are keyed by class name, so they must match the declared paths."""
    assert {
        class_name(task_spec.single_config_ref): task_type
        for task_type, task_spec in TASK_SPECS.items()
    } == test_module._SINGLE_CONFIG_NAME_INDEX
    assert {
        class_name(task_spec.scan_config_ref): task_type
        for task_type, task_spec in TASK_SPECS.items()
        if task_spec.scan_config_ref is not None
    } == test_module._SCAN_CONFIG_NAME_INDEX


def test_config_class_names_are_unique_across_task_specs():
    """Class names double as ``type`` discriminator values, so they must not collide."""
    names = [class_name(ref) for task_spec in TASK_SPECS.values() for ref in task_spec.config_refs]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("task_type", LAUNCH_SYSTEM_TASK_TYPES_WITHOUT_CONFIG_MAP)
def test_config_task_map_unregistered_task_type_raises(task_type: TaskType):
    with pytest.raises(KeyError, match="No task spec"):
        test_module.get_task_spec_for_task_type(task_type)


@pytest.mark.parametrize(
    ("task_type", "task_class"),
    [
        (TaskType.circuit_extraction, CircuitExtractionTask),
        (
            TaskType.ion_channel_model_simulation_execution,
            IonChannelModelSimulationExecutionTask,
        ),
        (
            TaskType.single_neuron_simulation_execution,
            SingleNeuronSimulationExecutionTask,
        ),
        (
            TaskType.single_neuron_synaptome_simulation_execution,
            SingleNeuronSynaptomeSimulationExecutionTask,
        ),
        (
            TaskType.circuit_simulation_neurodamus_machine,
            CircuitSimulationExecutionTask,
        ),
        (TaskType.morphology_skeletonization, SkeletonizationTask),
        (TaskType.circuit_single_build, MEModelSynapticModelPlacementTask),
    ],
)
def test_get_task_spec_for_task_type_task_cls(task_type, task_class):
    assert test_module.get_task_spec_for_task_type(task_type).task_cls is task_class


@pytest.mark.parametrize(
    ("task_type", "single_config_class"),
    [
        (TaskType.circuit_extraction, CircuitExtractionSingleConfig),
        (
            TaskType.ion_channel_model_simulation_execution,
            IonChannelModelSimulationExecutionSingleConfig,
        ),
        (
            TaskType.single_neuron_simulation_execution,
            SingleNeuronSimulationExecutionSingleConfig,
        ),
        (
            TaskType.single_neuron_synaptome_simulation_execution,
            SingleNeuronSynaptomeSimulationExecutionSingleConfig,
        ),
        (
            TaskType.circuit_simulation_neurodamus_machine,
            CircuitSimulationExecutionSingleConfig,
        ),
        (TaskType.morphology_skeletonization, SkeletonizationSingleConfig),
        (TaskType.circuit_single_build, MEModelSynapticModelPlacementSingleConfig),
    ],
)
def test_get_task_spec_for_task_type_single_config_cls(task_type, single_config_class):
    assert (
        test_module.get_task_spec_for_task_type(task_type).single_config_cls is single_config_class
    )


@pytest.mark.parametrize(
    ("task_type", "asset_label"),
    [
        (TaskType.circuit_extraction, AssetLabel.task_config),
        (TaskType.morphology_skeletonization, AssetLabel.task_config),
        (TaskType.circuit_single_build, AssetLabel.task_config),
        (TaskType.circuit_simulation, None),
        (TaskType.ion_channel_model_simulation_execution, None),
        (TaskType.single_neuron_simulation_execution, None),
        (TaskType.single_neuron_synaptome_simulation_execution, None),
        (TaskType.circuit_simulation_neurodamus_machine, None),
    ],
)
def test_get_task_spec_for_task_type_asset_label(task_type, asset_label):
    assert test_module.get_task_spec_for_task_type(task_type).asset_label is asset_label


@pytest.mark.parametrize(
    ("config_class", "task_class"),
    [
        (CircuitSimulationSingleConfig, GenerateSimulationTask),
        (CircuitExtractionSingleConfig, CircuitExtractionTask),
        (
            IonChannelModelSimulationSingleConfig,
            GenerateSimulationTask,
        ),
    ],
)
def test_get_task_spec_for_single_config_task_cls(config_class, task_class):
    task_spec = test_module.get_task_spec_for_single_config(config_class)
    assert task_spec is not None
    assert task_spec.task_cls is task_class


@pytest.mark.parametrize(
    "scan_config_class",
    [
        CircuitExtractionScanConfig,
        EMSynapseMappingScanConfig,
        SkeletonizationScanConfig,
    ],
)
def test_scan_config_does_not_dispatch_to_a_task(scan_config_class):
    """A ScanConfig may still hold multi-value parameters, so it is not executable."""
    config = MagicMock(spec=scan_config_class)
    with pytest.raises(KeyError, match="No task registered"):
        run_tasks.run_task_for_single_config(config)


def test_single_config_subclass_dispatches_via_its_base():
    """The Simulation alias subclasses CircuitSimulationSingleConfig without registering."""
    task_spec = test_module.get_task_spec_for_single_config(Simulation)
    assert task_spec is not None
    assert task_spec.task_cls is GenerateSimulationTask


def test_get_task_spec_for_task_type_returns_the_registered_spec():
    first = test_module.get_task_spec_for_task_type(TaskType.circuit_extraction)
    second = test_module.get_task_spec_for_task_type(TaskType.circuit_extraction)
    assert first is second is TASK_SPECS[TaskType.circuit_extraction]


def test_get_task_spec_for_scan_config_unregistered_class_returns_none():
    class UnregisteredScanConfig:
        pass

    assert test_module.get_task_spec_for_scan_config(UnregisteredScanConfig) is None


def test_get_task_spec_for_single_config_unregistered_class_returns_none():
    class UnregisteredSingleConfig:
        pass

    assert test_module.get_task_spec_for_single_config(UnregisteredSingleConfig) is None


def test_lookup_is_by_class_name_not_by_identity():
    """A class that merely shares a registered name resolves to that spec.

    The indexes are keyed by ``__qualname__`` because that is the ``type`` discriminator
    value, which is what a serialized config carries. ``run_tasks`` still guards dispatch
    with an ``issubclass`` check, so a same-named impostor cannot be executed.
    """
    impostor = type("CircuitExtractionSingleConfig", (), {})

    task_spec = test_module.get_task_spec_for_single_config(impostor)

    assert task_spec is TASK_SPECS[TaskType.circuit_extraction]
    with pytest.raises(KeyError, match="No task registered"):
        run_tasks.run_task_for_single_config(impostor())


def test_scan_config_class_is_not_in_the_single_config_index():
    """A ScanConfig must not resolve through the SingleConfig lookup."""
    assert test_module.get_task_spec_for_single_config(CircuitExtractionScanConfig) is None


def test_emodel_optimization_declares_its_optional_dependency():
    assert TASK_SPECS[TaskType.emodel_optimization].requires_package == "bluepyemodel"


@patch(
    "obi_one.scientific.mappings_and_registry.config_task_map.find_spec",
    return_value=None,
)
def test_get_task_spec_for_task_type_emodel_unavailable_raises(mock_find_spec):
    with pytest.raises(KeyError, match="No task spec"):
        test_module.get_task_spec_for_task_type(TaskType.emodel_optimization)

    mock_find_spec.assert_called_once_with("bluepyemodel")


@patch(
    "obi_one.scientific.mappings_and_registry.config_task_map.find_spec",
    side_effect=ImportError("blocked"),
)
def test_is_task_type_available_treats_blocked_package_as_missing(mock_find_spec):
    assert test_module._is_task_type_available(TaskType.emodel_optimization) is False
    mock_find_spec.assert_called_once_with("bluepyemodel")

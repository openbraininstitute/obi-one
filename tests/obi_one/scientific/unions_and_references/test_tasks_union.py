"""``TasksUnion`` membership stays aligned with ``TASK_SPECS``."""

from unittest.mock import MagicMock, patch

from obi_one.core.task import Task
from obi_one.scientific.mappings_and_registry import config_task_map
from obi_one.scientific.mappings_and_registry.config_task_map import TASK_SPECS
from obi_one.scientific.unions_and_references import tasks
from obi_one.types import TaskType
from obi_one.utils.lazy_import import class_name, import_class


def test_task_union_members_match_iter_task_refs():
    expected_names = {class_name(ref) for ref in config_task_map.iter_task_refs()}
    actual_names = {member.__name__ for member in tasks._TASK_MEMBERS}
    assert actual_names == expected_names


def test_task_union_members_are_task_subclasses():
    for class_ref in config_task_map.iter_task_refs():
        cls = import_class(class_ref)
        assert issubclass(cls, Task)


def test_iter_task_refs_deduplicates_task_names_across_task_specs():
    shared_ref = TASK_SPECS[TaskType.circuit_simulation].task_ref
    patched_specs = {
        TaskType.circuit_simulation: MagicMock(task_ref=shared_ref),
        TaskType.me_model_simulation: MagicMock(task_ref=shared_ref),
    }
    with (
        patch.object(config_task_map, "TASK_SPECS", patched_specs),
        patch.object(config_task_map, "_is_task_type_available", return_value=True),
    ):
        assert tuple(config_task_map.iter_task_refs()) == (shared_ref,)


def test_iter_task_refs_skips_unavailable_task_types():
    patched_specs = {
        TaskType.circuit_extraction: MagicMock(
            task_ref=TASK_SPECS[TaskType.circuit_extraction].task_ref,
        ),
        TaskType.emodel_optimization: MagicMock(
            task_ref=TASK_SPECS[TaskType.emodel_optimization].task_ref,
        ),
    }

    def available(task_type: TaskType) -> bool:
        return task_type is not TaskType.emodel_optimization

    with (
        patch.object(config_task_map, "TASK_SPECS", patched_specs),
        patch.object(config_task_map, "_is_task_type_available", side_effect=available),
    ):
        refs = tuple(config_task_map.iter_task_refs())
        assert class_name(TASK_SPECS[TaskType.emodel_optimization].task_ref) not in {
            class_name(ref) for ref in refs
        }

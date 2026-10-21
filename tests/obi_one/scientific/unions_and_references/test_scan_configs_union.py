"""``ScanConfigsUnion`` membership stays aligned with ``TASK_SPECS``."""

from unittest.mock import MagicMock, patch

from obi_one.core.scan_config import ScanConfig
from obi_one.scientific.mappings_and_registry import config_task_map
from obi_one.scientific.mappings_and_registry.config_task_map import TASK_SPECS
from obi_one.scientific.unions_and_references import scan_configs
from obi_one.types import TaskType
from obi_one.utils.lazy_import import class_name, import_class


def test_scan_config_union_members_match_iter_scan_config_refs():
    expected_names = {class_name(ref) for ref in config_task_map.iter_scan_config_refs()}
    actual_names = {member.__name__ for member in scan_configs._SCAN_CONFIG_MEMBERS}
    assert actual_names == expected_names


def test_scan_config_union_members_are_scan_config_subclasses():
    for class_ref in config_task_map.iter_scan_config_refs():
        cls = import_class(class_ref)
        assert issubclass(cls, ScanConfig)


def test_iter_scan_config_refs_deduplicates_scan_config_names_across_task_specs():
    shared_ref = TASK_SPECS[TaskType.circuit_extraction].scan_config_ref
    patched_specs = {
        TaskType.circuit_extraction: MagicMock(scan_config_ref=shared_ref),
        TaskType.folder_compression: MagicMock(scan_config_ref=shared_ref),
    }
    with (
        patch.object(config_task_map, "TASK_SPECS", patched_specs),
        patch.object(config_task_map, "_is_task_type_available", return_value=True),
        patch.object(config_task_map, "_SCAN_CONFIG_EXTRA_REFS", ()),
    ):
        assert config_task_map.iter_scan_config_refs() == (shared_ref,)


def test_iter_scan_config_refs_skips_extra_ref_when_name_already_listed():
    scan_ref = TASK_SPECS[TaskType.circuit_extraction].scan_config_ref
    with patch.object(config_task_map, "_SCAN_CONFIG_EXTRA_REFS", (scan_ref,)):
        refs = config_task_map.iter_scan_config_refs()
        assert refs.count(scan_ref) == 1

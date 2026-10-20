"""``ScanConfigsUnion`` membership stays aligned with ``TASK_SPECS``."""

from obi_one.core.scan_config import ScanConfig
from obi_one.scientific.mappings_and_registry import config_task_map
from obi_one.scientific.unions_and_references import scan_configs
from obi_one.utils.lazy_import import class_name, import_class


def test_scan_config_union_members_match_iter_scan_config_refs():
    expected_names = {class_name(ref) for ref in config_task_map.iter_scan_config_refs()}
    actual_names = {member.__name__ for member in scan_configs._SCAN_CONFIG_MEMBERS}
    assert actual_names == expected_names


def test_scan_config_union_members_are_scan_config_subclasses():
    for class_ref in config_task_map.iter_scan_config_refs():
        cls = import_class(class_ref)
        assert issubclass(cls, ScanConfig)

"""Compatibility re-exports; implementation moved to obi_one_lazy."""

# ruff: file-ignore[unused-import, unsorted-imports]

from obi_one_lazy.core.deserialize import (
    deserialize_json_dict_to_form,
    deserialize_obi_object_from_json_data,
    deserialize_obi_object_from_json_file,
    load_class,
    load_json,
    OBIBaseModel,
    Path,
    ScanConfig,
    TypeAdapter,
)

__all__ = [
    "deserialize_json_dict_to_form",
    "deserialize_obi_object_from_json_data",
    "deserialize_obi_object_from_json_file",
    "load_class",
    "load_json",
    "OBIBaseModel",
    "Path",
    "ScanConfig",
    "TypeAdapter",
]

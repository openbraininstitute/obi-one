import json
from pathlib import Path

from pydantic import TypeAdapter

from obi_one.core.base import OBIBaseModel
from obi_one.core.registry import type_registry
from obi_one.core.scan_config import ScanConfig


def deserialize_obi_object_from_json_data(json_dict: dict) -> OBIBaseModel:
    cls = type_registry.get(json_dict["type"])
    return cls.model_validate(json_dict)  # ty:ignore[unresolved-attribute]


def deserialize_obi_object_from_json_file(json_path: Path) -> OBIBaseModel:
    with Path.open(json_path) as file:
        json_dict = json.load(file)
    return deserialize_obi_object_from_json_data(json_dict)


def deserialize_json_dict_to_form(json_dict: dict) -> OBIBaseModel:
    adapter = TypeAdapter(ScanConfig)
    return adapter.validate_python(json_dict)

import json
from pathlib import Path

from pydantic import TypeAdapter

import obi_one as obi
from obi_one.core.scan_config import ScanConfig


def deserialize_obi_object_from_json_data(json_dict: dict) -> obi.OBIBaseModel:
    obi_object = getattr(obi, json_dict["type"]).model_validate(json_dict)
    return obi_object


def deserialize_obi_object_from_json_file(json_path: Path) -> obi.OBIBaseModel:
    with Path.open(json_path) as file:
        json_dict = json.load(file)
    return deserialize_obi_object_from_json_data(json_dict)


def deserialize_json_dict_to_form(json_dict: dict) -> obi.OBIBaseModel:
    adapter = TypeAdapter(ScanConfig)
    return adapter.validate_python(json_dict)

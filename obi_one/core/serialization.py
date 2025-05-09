from typing import Any

from entitysdk.models.entity import Entity


def entity_encoder(obj: Any) -> dict[str, str]:
    """Encode an Entity into a JSON-serializable dictionary."""
    cls_name = obj.__class__.__name__
    if issubclass(obj.__class__, Entity) and "FromID" not in cls_name:
        return {"type": f"{cls_name}FromID", "id_str": str(obj.id)}
    if "FromID" in cls_name:
        return {"type": cls_name, "id_str": str(obj.id)}
    raise TypeError(f"Object of type {cls_name} is not JSON serializable")


import json

import obi_one as obi


def deserialize_obi_object_from_json_data(json_data):
    obi_object = getattr(obi, json_data["type"]).model_validate(json_data)
    return obi_object


def deserialize_obi_object_from_json_file(json_path):
    with open(json_path) as file:
        data = json.load(file)
        return deserialize_obi_object_from_json_data(data)

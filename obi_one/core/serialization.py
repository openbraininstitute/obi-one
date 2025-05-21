import json
from pathlib import Path
from typing import Any

from entitysdk.models.entity import Entity

import obi_one as obi


def entity_encoder(obj: Any) -> dict[str, str]:
    """Encode an Entity into a JSON-serializable dictionary."""
    cls_name = obj.__class__.__name__
    if issubclass(obj.__class__, Entity) and "FromID" not in cls_name:
        return {"type": f"{cls_name}FromID", "id_str": str(obj.id)}
    if "FromID" in cls_name:
        return {"type": cls_name, "id_str": str(obj.id)}
    msg = f"Object of type {cls_name} is not JSON serializable"
    raise TypeError(msg)


def deserialize_obi_object_from_json_data(json_dict: dict) -> obi.OBIBaseModel:
    obi_object = getattr(obi, json_dict["type"]).model_validate(json_dict)
    return obi_object


def deserialize_obi_object_from_json_file(json_path: Path) -> obi.OBIBaseModel:
    with Path.open(json_path) as file:
        json_dict = json.load(file)
    return deserialize_obi_object_from_json_data(json_dict)

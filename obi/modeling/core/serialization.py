import obi
import json

def deserialize_obi_object_json(json_path):
    with open(json_path, "r") as file:
        data = json.load(file)
        obi_object = getattr(obi, data["obi_class"]).model_validate(data)
    return obi_object
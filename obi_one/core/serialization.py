import obi
import json

def deserialize_obi_object_from_json_data(json_data):
    obi_object = getattr(obi, json_data["type"]).model_validate(json_data)
    return obi_object

def deserialize_obi_object_from_json_file(json_path):
    with open(json_path, "r") as file:
        data = json.load(file)
        return deserialize_obi_object_from_json_data(data)
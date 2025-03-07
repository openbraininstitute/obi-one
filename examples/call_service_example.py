import requests
import obi
grid_scan = obi.deserialize_obi_object_from_json_file("../obi_output/circuit_simulations/grid_scan/generate_scan_config.json")
grid_scan_obi_json_serialization = grid_scan.serialize()

print(grid_scan_obi_json_serialization)

print(request.get("http://127.0.0.1:8000/openapi.json"))
# google json schema - official definition

requests.post("http://127.0.0.1:8000/simulationsform/set_form/", json=grid_scan_obi_json_serialization['form']).json()
requests.post("http://127.0.0.1:8000/simulationsform/generate_grid_scan/")
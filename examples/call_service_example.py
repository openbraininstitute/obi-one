import requests
import obi

# params = {
# 	'name': "test",
# 	'id': 1
# }
# print(requests.post("http://127.0.0.1:8000/circuitsimulation/", json=params).json())
# print(requests.get("http://127.0.0.1:8000/circuitsimulation/1").json())
# print(requests.get("http://127.0.0.1:8000/circuitsimulation/generate/1").json())

# print(requests.get("http://127.0.0.1:8000/simulationsform/generate/1").json()) # 


# params = {
#   "timestamps": {
#     "additionalProp1": {
#       "start_time": 0
#     },
#     "additionalProp2": {
#       "start_time": 0
#     },
#     "additionalProp3": {
#       "start_time": 0
#     }
#   },
#   "stimuli": {
#     "additionalProp1": {
#       "synapse_set": {
#         "circuit": {
#           "circuit_path": "string",
#           "node_set": "string"
#         }
#       },
#       "timestamps": {
#         "start_time": 0
#       }
#     },
#     "additionalProp2": {
#       "synapse_set": {
#         "circuit": {
#           "circuit_path": "string",
#           "node_set": "string"
#         }
#       },
#       "timestamps": {
#         "start_time": 0
#       }
#     },
#     "additionalProp3": {
#       "synapse_set": {
#         "circuit": {
#           "circuit_path": "string",
#           "node_set": "string"
#         }
#       },
#       "timestamps": {
#         "start_time": 0
#       }
#     }
#   },
#   "recordings": {
#     "additionalProp1": {
#       "start_time": 0,
#       "end_time": 0
#     },
#     "additionalProp2": {
#       "start_time": 0,
#       "end_time": 0
#     },
#     "additionalProp3": {
#       "start_time": 0,
#       "end_time": 0
#     }
#   },
#   "neuron_sets": {
#     "additionalProp1": {
#       "circuit": {
#         "circuit_path": "string",
#         "node_set": "string"
#       }
#     },
#     "additionalProp2": {
#       "circuit": {
#         "circuit_path": "string",
#         "node_set": "string"
#       }
#     },
#     "additionalProp3": {
#       "circuit": {
#         "circuit_path": "string",
#         "node_set": "string"
#       }
#     }
#   },
#   "synapse_sets": {
#     "additionalProp1": {
#       "circuit": {
#         "circuit_path": "string",
#         "node_set": "string"
#       }
#     },
#     "additionalProp2": {
#       "circuit": {
#         "circuit_path": "string",
#         "node_set": "string"
#       }
#     },
#     "additionalProp3": {
#       "circuit": {
#         "circuit_path": "string",
#         "node_set": "string"
#       }
#     }
#   },
#   "intracellular_location_sets": {
#     "additionalProp1": {
#       "neuron_ids": [
#         0
#       ],
#       "section": "string"
#     },
#     "additionalProp2": {
#       "neuron_ids": [
#         0
#       ],
#       "section": "string"
#     },
#     "additionalProp3": {
#       "neuron_ids": [
#         0
#       ],
#       "section": "string"
#     }
#   },
#   "extracellular_location_sets": {
#     "additionalProp1": {},
#     "additionalProp2": {},
#     "additionalProp3": {}
#   },
#   "initialize": {
#     "circuit": {
#       "circuit_path": "string",
#       "node_set": "string"
#     },
#     "simulation_length": 100,
#     "random_seed": 1,
#     "extracellular_calcium_concentration": 1.1,
#     "v_init": -80,
#     "sonata_version": 1,
#     "target_simulator": "CORENEURON",
#     "timestep": 0.025
#   }
# }

# requests.post("http://127.0.0.1:8000/simulationsform/create_form/", json=grid_scan.form.model_dump()).json()


grid_scan = obi.deserialize_obi_object_from_json_file("../obi_output/circuit_simulations/grid_scan/generate_scan_config.json")
grid_scan_obi_json_serialization = grid_scan.serialize()
requests.post("http://127.0.0.1:8000/simulationsform/set_form/", json=grid_scan_obi_json_serialization['form']).json()
requests.post("http://127.0.0.1:8000/simulationsform/generate_grid_scan/")
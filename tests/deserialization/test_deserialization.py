import json

import pytest

import obi_one as obi

from tests.utils import DATA_DIR


def test_deserialization(tmp_path):

    simulation_json_path = DATA_DIR / "circuit_simulation_single_config_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = obi.deserialize_obi_object_from_json_data(data)
    simulation.coordinate_output_root = tmp_path / "simulation_output"
    obi.run_task_for_single_config(single_config=simulation)

    simulation = obi.deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, obi.CircuitSimulationSingleConfig)
    simulation.coordinate_output_root = tmp_path / "simulation_output_2"
    obi.run_task_for_single_config(single_config=simulation)


    simulation_json_path = DATA_DIR / "deprecated_simulation_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = obi.deserialize_obi_object_from_json_data(data)
    simulation.coordinate_output_root = tmp_path / "simulation_output_3"
    obi.run_task_for_single_config(single_config=simulation)

    simulation = obi.deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, obi.Simulation)
    simulation.coordinate_output_root = tmp_path / "simulation_output_4"
    obi.run_task_for_single_config(single_config=simulation)

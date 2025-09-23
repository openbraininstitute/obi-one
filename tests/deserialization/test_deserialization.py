import json

import pytest

import obi_one as obi

from tests.utils import DATA_DIR


@pytest.fixture
def simulation_json():
    return json.loads((DATA_DIR / "simulation_serialization.json").read_bytes())


def run_task_for_single_simulation_generation_config(single_config):
    task_type = obi.get_task_config_type(single_config)
    task = task_type(config=single_config)
    task.execute()


def test_deserialization(tmp_path):
    simulation_json_path = DATA_DIR / "simulation_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = obi.deserialize_obi_object_from_json_data(data)
    assert isinstance(simulation, obi.Simulation)
    simulation.coordinate_output_root = tmp_path / "simulation_output"
    run_task_for_single_simulation_generation_config(single_config=simulation)

    simulation = obi.deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, obi.Simulation)
    simulation.coordinate_output_root = tmp_path / "simulation_output_2"
    run_task_for_single_simulation_generation_config(single_config=simulation)

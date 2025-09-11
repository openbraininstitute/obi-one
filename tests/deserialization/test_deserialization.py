import pytest
import json

from tests.utils import DATA_DIR

import obi_one as obi

@pytest.fixture
def simulation_json():
    return json.loads((DATA_DIR / "simulation_serialization.json").read_bytes())


def test_deserialization():

    simulation_json_path = DATA_DIR / "simulation_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = obi.deserialize_obi_object_from_json_data(data)
    assert isinstance(simulation, obi.Simulation)

    simulation = obi.deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, obi.Simulation)



    
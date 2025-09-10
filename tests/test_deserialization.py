import pytest
import json

from tests.utils import DATA_DIR

@pytest.fixture
def simulation_json():
    return json.loads((DATA_DIR / "simulation_serialization.json").read_bytes())


@pytest.fixture
def ephys_nwb():
    return (DATA_DIR / "S1FL_L5_DBC_cIR_4.nwb").read_bytes()


def test_deserialization():
    
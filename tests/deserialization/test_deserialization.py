import json

import obi_one as obi

from tests.utils import DATA_DIR


def test_deserialization(tmp_path):


    """
    Test deserialization of simulation
    """
    simulation_json_path = DATA_DIR / "circuit_simulation_single_config_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = obi.deserialize_obi_object_from_json_data(data)
    assert isinstance(simulation, obi.CircuitSimulationSingleConfig)
    simulation.coordinate_output_root = tmp_path / "simulation_output"
    obi.run_task_for_single_config(single_config=simulation)

    simulation = obi.deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, obi.CircuitSimulationSingleConfig)
    simulation.coordinate_output_root = tmp_path / "simulation_output_2"
    obi.run_task_for_single_config(single_config=simulation)

    """
    Test deserialization of simulation campaign
    """
    simulation_campaign_json_path = DATA_DIR / "grid_scan_serialization.json"

    data = json.loads(simulation_campaign_json_path.read_bytes())
    simulation_campaign = obi.deserialize_obi_object_from_json_data(data)
    assert isinstance(simulation_campaign, obi.GridScanGenerationTask)
    simulation_campaign.output_root = tmp_path / "simulation_output_3"
    simulation_campaign.execute()

    simulation_campaign = obi.deserialize_obi_object_from_json_file(simulation_campaign_json_path)
    assert isinstance(simulation_campaign, obi.GridScanGenerationTask)
    simulation_campaign.output_root = tmp_path / "simulation_output_4"
    simulation_campaign.execute()



    """
    Test deserialization of depreceted simulation (based on SimulationsForm)
    """
    simulation_json_path = DATA_DIR / "deprecated_simulation_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = obi.deserialize_obi_object_from_json_data(data)
    simulation.coordinate_output_root = tmp_path / "simulation_output_5"
    obi.run_task_for_single_config(single_config=simulation)

    simulation = obi.deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, obi.Simulation)
    simulation.coordinate_output_root = tmp_path / "simulation_output_6"
    obi.run_task_for_single_config(single_config=simulation)

import json

import obi_one as obi

from tests.utils import DATA_DIR


def test_deserialization(tmp_path):
    model_dumps_dir = DATA_DIR / "model_dumps"

    """
    Test deserialization of simulation
    """
    simulation_json_path = model_dumps_dir / "circuit_simulation_single_config_serialization.json"

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
    Test deserialization of grid_scan_task
    """
    grid_scan_task_json_path = model_dumps_dir / "grid_scan_task_serialization.json"

    data = json.loads(grid_scan_task_json_path.read_bytes())
    grid_scan_task = obi.deserialize_obi_object_from_json_data(data)
    assert isinstance(grid_scan_task, obi.GridScanGenerationTask)
    grid_scan_task.output_root = tmp_path / "simulation_output_3"
    grid_scan_task.execute()
    obi.run_tasks_for_generated_scan(grid_scan_task)

    grid_scan_task = obi.deserialize_obi_object_from_json_file(grid_scan_task_json_path)
    assert isinstance(grid_scan_task, obi.GridScanGenerationTask)
    grid_scan_task.output_root = tmp_path / "simulation_output_4"
    grid_scan_task.execute()
    obi.run_tasks_for_generated_scan(grid_scan_task)

    """
    Test deserialization of depreceted simulation (based on SimulationsForm)
    """
    simulation_json_path = model_dumps_dir / "deprecated_simulation_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = obi.deserialize_obi_object_from_json_data(data)
    simulation.coordinate_output_root = tmp_path / "simulation_output_5"
    obi.run_task_for_single_config(single_config=simulation)

    simulation = obi.deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, obi.Simulation)
    simulation.coordinate_output_root = tmp_path / "simulation_output_6"
    obi.run_task_for_single_config(single_config=simulation)

    """
    Test deserialization of deprecated grid_scan_simulations_form (GridScan, SimulationsForm)
    """
    grid_scan_json_path = model_dumps_dir / "grid_scan_simulations_form.json"

    data = json.loads(grid_scan_json_path.read_bytes())
    grid_scan = obi.deserialize_obi_object_from_json_data(data)
    assert isinstance(grid_scan, obi.GridScan)
    grid_scan.output_root = tmp_path / "simulation_output_7"
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

    grid_scan = obi.deserialize_obi_object_from_json_file(grid_scan_json_path)
    assert isinstance(grid_scan, obi.GridScan)
    grid_scan.output_root = tmp_path / "simulation_output_8"
    grid_scan.execute()
    obi.run_tasks_for_generated_scan(grid_scan)

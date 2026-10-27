import json

import pytest
from pydantic import ValidationError

from obi_one.core.deserialize import (
    deserialize_obi_object_from_json_data,
    deserialize_obi_object_from_json_file,
)
from obi_one.core.run_tasks import (
    run_task_for_single_config,
    run_tasks_for_generated_scan,
)
from obi_one.core.scan import GridScan
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.blocks.stimuli.stimulus import ConstantCurrentClampSomaticStimulus
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)

from tests.utils import CIRCUIT_DIR, DATA_DIR

MODEL_DUMPS_DIR = DATA_DIR / "model_dumps"

# Legacy serializations that still contain the now-deprecated ``NeuronSetReference`` (and the
# deprecated neuron sets it referenced, e.g. ``AllNeurons``). Deserializing any of these must fail
# loudly with a migration message rather than silently producing a broken config.
DEPRECATED_SERIALIZATION_FILES = [
    "circuit_simulation_single_config_serialization_deprecated.json",
    "grid_scan_task_serialization_deprecated.json",
    "grid_scan_simulations_form_deprecated.json",
]


def test_deserialization(tmp_path):
    model_dumps_dir = MODEL_DUMPS_DIR

    # Test deserialization of simulation
    simulation_json_path = model_dumps_dir / "circuit_simulation_single_config_serialization.json"

    data = json.loads(simulation_json_path.read_bytes())
    simulation = deserialize_obi_object_from_json_data(data)
    assert isinstance(simulation, CircuitSimulationSingleConfig)
    simulation.coordinate_output_root = tmp_path / "simulation_output"
    run_task_for_single_config(single_config=simulation)

    simulation = deserialize_obi_object_from_json_file(simulation_json_path)
    assert isinstance(simulation, CircuitSimulationSingleConfig)
    simulation.coordinate_output_root = tmp_path / "simulation_output_2"
    run_task_for_single_config(single_config=simulation)

    # Test deserialization of grid_scan_task
    grid_scan_task_json_path = model_dumps_dir / "grid_scan_task_serialization.json"

    data = json.loads(grid_scan_task_json_path.read_bytes())
    grid_scan_task = deserialize_obi_object_from_json_data(data)
    assert isinstance(grid_scan_task, GridScanGenerationTask)
    grid_scan_task.output_root = tmp_path / "simulation_output_3"
    grid_scan_task.execute()
    run_tasks_for_generated_scan(grid_scan_task)

    grid_scan_task = deserialize_obi_object_from_json_file(grid_scan_task_json_path)
    assert isinstance(grid_scan_task, GridScanGenerationTask)
    grid_scan_task.output_root = tmp_path / "simulation_output_4"
    grid_scan_task.execute()
    run_tasks_for_generated_scan(grid_scan_task)

    # Test deserialization of deprecated grid_scan_simulations_form (GridScan, SimulationsForm).
    # The deprecated top-level GridScan/SimulationsForm aliases must still deserialize and run; the
    # neuron sets and references it uses are the current (non-deprecated) types.
    grid_scan_json_path = model_dumps_dir / "grid_scan_simulations_form.json"

    data = json.loads(grid_scan_json_path.read_bytes())
    grid_scan = deserialize_obi_object_from_json_data(data)
    assert isinstance(grid_scan, GridScan)
    grid_scan.output_root = tmp_path / "simulation_output_7"
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)

    grid_scan = deserialize_obi_object_from_json_file(grid_scan_json_path)
    assert isinstance(grid_scan, GridScan)
    grid_scan.output_root = tmp_path / "simulation_output_8"
    grid_scan.execute()
    run_tasks_for_generated_scan(grid_scan)


def test_deserialization_somatic_stimulus_type():
    data = {
        "type": "CircuitSimulationScanConfig",
        "info": {
            "type": "Info",
            "campaign_name": "test",
            "campaign_description": "test",
        },
        "initialize": {
            "type": "CircuitSimulationScanConfig.Initialize",
            "circuit": {
                "type": "Circuit",
                "name": "dummy",
                "path": str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
                "matrix_path": None,
            },
            "node_set": None,
            "simulation_length": 100.0,
            "extracellular_calcium_concentration": 1.1,
            "v_init": -80.0,
            "random_seed": 1,
        },
        "stimuli": {
            "LegacyStimulus": {
                "type": "ConstantCurrentClampSomaticStimulus",
                "duration": 10.0,
                "amplitude": 0.2,
                "timestamps": None,
                "timestamp_offset": 5.0,
                "neuron_set": None,
            }
        },
        "recordings": {},
        "timestamps": {},
        "neuron_sets": {},
        "synaptic_manipulations": {},
        "morphology_locations": {},
        "distributions": {},
    }

    config = deserialize_obi_object_from_json_data(data)

    stimulus = config.stimuli["LegacyStimulus"]

    assert isinstance(stimulus, ConstantCurrentClampSomaticStimulus)
    assert stimulus.type == "ConstantCurrentClampSomaticStimulus"


@pytest.mark.parametrize("filename", DEPRECATED_SERIALIZATION_FILES)
def test_deserialization_of_deprecated_neuron_set_reference_raises(filename):
    """Legacy configs using the deprecated NeuronSetReference must fail to deserialize.

    The error must clearly direct the user to the replacement reference types rather than surfacing
    an obscure error (e.g. a missing-setter ``AttributeError``).
    """
    deprecated_json_path = MODEL_DUMPS_DIR / filename

    data = json.loads(deprecated_json_path.read_bytes())
    with pytest.raises(ValueError, match="NeuronSetReference is deprecated"):
        deserialize_obi_object_from_json_data(data)

    with pytest.raises(ValueError, match="NeuronSetReference is deprecated"):
        deserialize_obi_object_from_json_file(deprecated_json_path)


@pytest.mark.parametrize("filename", DEPRECATED_SERIALIZATION_FILES)
def test_deprecated_neuron_set_reference_is_wrapped_by_pydantic(filename):
    """The deprecation must surface as a pydantic ValidationError, not a bare exception."""
    data = json.loads((MODEL_DUMPS_DIR / filename).read_bytes())

    with pytest.raises(ValidationError, match="NeuronSetReference is deprecated"):
        deserialize_obi_object_from_json_data(data)

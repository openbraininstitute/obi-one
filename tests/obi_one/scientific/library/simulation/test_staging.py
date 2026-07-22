from unittest.mock import MagicMock, patch

import pytest
from obi_one.scientific.library.simulation.schemas import (
    BluecellulabSimulationParameters,
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    NeuronMechanismBuild,
)

from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.simulation import staging as test_module
from obi_one.types import SimulationBackend


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dummy")
    return path


def test_stage_ion_channel_models_as_circuit(monkeypatch, tmp_path):
    mock_stage_sonata = MagicMock()
    mock_me_model = MagicMock()

    monkeypatch.setattr(
        "obi_one.scientific.library.simulation.staging.stage_sonata_from_config",
        mock_stage_sonata,
    )
    monkeypatch.setattr(
        "obi_one.scientific.library.simulation.staging.MEModelCircuit",
        mock_me_model,
    )

    mock_client = MagicMock()
    mock_output_dir = tmp_path / "output"

    class MockIonChannel:
        id_str = "ic1"

        @staticmethod
        def has_conductance(db_client):  # noqa: ARG004
            return True

        @staticmethod
        def get_conductance_name(db_client):  # noqa: ARG004
            return "gbar"

    class MockICData:
        ion_channel_model = MockIonChannel()
        conductance = 1.23

    mock_ion_channel_models = {"ic1": MockICData()}
    mock_stage_sonata.return_value = mock_output_dir / "circuit.json"

    mock_instance = MagicMock()
    mock_me_model.return_value = mock_instance

    circuit = test_module.stage_ion_channel_models_as_circuit(
        client=mock_client, ion_channel_models=mock_ion_channel_models, output_dir=mock_output_dir
    )

    assert circuit == mock_instance
    mock_stage_sonata.assert_called_once()
    mock_me_model.assert_called_once_with(
        name="single_cell", path=str(mock_output_dir / "circuit.json")
    )


def test_stage_memodel_as_circuit_from_id(monkeypatch, tmp_path):
    mock_stage_sonata = MagicMock()
    mock_build_circuit = MagicMock()

    monkeypatch.setattr(
        "obi_one.scientific.library.simulation.staging.stage_sonata_from_memodel",
        mock_stage_sonata,
    )
    monkeypatch.setattr(
        "obi_one.scientific.library.simulation.staging._build_memodel_circuit",
        mock_build_circuit,
    )

    mock_client = MagicMock()
    mock_output_dir = tmp_path / "output"
    mock_memodel_entity = MagicMock()
    circuit_config_path = mock_output_dir / "circuit.json"
    mock_stage_sonata.return_value = circuit_config_path
    expected = MagicMock()
    mock_build_circuit.return_value = expected

    with patch.object(MEModelFromID, "entity", return_value=mock_memodel_entity):
        circuit = test_module.stage_memodel_as_circuit(
            client=mock_client,
            circuit=MEModelFromID(id_str="memodel-id"),
            output_dir=mock_output_dir,
        )

    assert circuit is expected
    mock_stage_sonata.assert_called_once_with(
        client=mock_client,
        memodel=mock_memodel_entity,
        output_dir=mock_output_dir,
    )
    mock_build_circuit.assert_called_once_with(circuit_config_path)


@pytest.mark.parametrize(
    ("simulation_backend", "expected_type"),
    [
        (SimulationBackend.bluecellulab, BluecellulabSimulationParameters),
        (SimulationBackend.neurodamus, NeurodamusSimulationParameters),
    ],
)
def test_get_simulation_parameters_success(
    monkeypatch, tmp_path, simulation_backend, expected_type
):
    mock_load_json = MagicMock()
    simulation_config_file = tmp_path / "config.json"
    neuron_mechanism_build = NeuronMechanismBuild(
        libnrnmech_path=_touch(tmp_path / "libnrnmech.so")
    )
    neurodamus_mechanism_build = NeurodamusMechanismBuild(
        libnrnmech_path=_touch(tmp_path / "libnrnmech.so"),
        libcorenrnmech_path=_touch(tmp_path / "libcorenrnmech.so"),
        special_binary_path=_touch(tmp_path / "special"),
    )
    mechanism_build = (
        neuron_mechanism_build
        if simulation_backend == SimulationBackend.bluecellulab
        else neurodamus_mechanism_build
    )

    mock_load_json.side_effect = [
        {"node_sets_file": "nodes.json", "node_set": "All", "run": {"tstop": 100}},
        {"All": {"node_id": [1, 2, 3]}},
    ]
    monkeypatch.setattr("obi_one.scientific.library.simulation.staging.load_json", mock_load_json)

    params = test_module.get_simulation_parameters(
        simulation_backend=simulation_backend,
        simulation_config_file=simulation_config_file,
        mechanism_build=mechanism_build,
    )

    assert isinstance(params, expected_type)
    assert params.number_of_cells == 3
    assert params.stop_time == 100
    assert params.config_file == simulation_config_file
    assert params.mechanism_build == mechanism_build


def test_get_simulation_parameters_missing_node_set(monkeypatch, tmp_path):
    mock_load_json = MagicMock()
    simulation_config_file = tmp_path / "config.json"
    mechanism_build = NeuronMechanismBuild(libnrnmech_path=_touch(tmp_path / "libnrnmech.so"))

    mock_load_json.side_effect = [
        {"node_sets_file": "nodes.json", "node_set": "Foo", "run": {"tstop": 100}},
        {"All": {"node_id": [1, 2, 3]}},
    ]
    monkeypatch.setattr("obi_one.scientific.library.simulation.staging.load_json", mock_load_json)

    with pytest.raises(KeyError, match="Node set 'Foo' not found"):
        test_module.get_simulation_parameters(
            simulation_backend=SimulationBackend.bluecellulab,
            simulation_config_file=simulation_config_file,
            mechanism_build=mechanism_build,
        )

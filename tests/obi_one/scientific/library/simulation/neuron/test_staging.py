from unittest.mock import MagicMock, patch

import pytest

from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.library.simulation.neuron.schemas import (
    BluecellulabSimulationParameters,
    NeurodamusMechanismBuild,
    NeurodamusSimulationParameters,
    NeuronMechanismBuild,
)
from obi_one.types import SimulationBackend
from obi_one_lazy.scientific.library.simulation.neuron import staging as test_module

from tests.obi_one.scientific.library.simulation.neuron._fakes import make_fake_resolution


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dummy")
    return path


def _patch_node_set_resolution(monkeypatch, per_node_set, *, node_set, **kwargs):
    """Patch staging's libsonata.SimulationConfig and the node-set resolver.

    Returns the fake SimulationConfig so callers can assert on it if needed.
    """
    simulation_config, node_sets, circuit_config = make_fake_resolution(
        per_node_set, node_set=node_set, **kwargs
    )
    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.libsonata.SimulationConfig.from_file",
        lambda _path: simulation_config,
    )
    monkeypatch.setattr(
        "obi_one.utils.circuit._merged_simulation_node_sets",
        lambda _sim_cfg: (node_sets, circuit_config),
    )
    return simulation_config


def test_stage_ion_channel_models_as_circuit(monkeypatch, tmp_path):
    mock_stage_sonata = MagicMock()
    mock_me_model = MagicMock()

    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.stage_sonata_from_config",
        mock_stage_sonata,
    )
    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.MEModelCircuit",
        mock_me_model,
    )

    mock_client = MagicMock()
    mock_output_dir = tmp_path / "output"

    class MockIonChannel:
        id_str = "ic1"

        @staticmethod
        def has_conductance(db_client):  # ruff: ignore[unused-static-method-argument]
            return True

        @staticmethod
        def get_conductance_name(db_client):  # ruff: ignore[unused-static-method-argument]
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
        "obi_one_lazy.scientific.library.simulation.neuron.staging.stage_sonata_from_memodel",
        mock_stage_sonata,
    )
    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging._build_memodel_circuit",
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
        max_concurrent=1,
    )
    mock_build_circuit.assert_called_once_with(circuit_config_path)


def test_stage_memodel_as_circuit_forwards_max_concurrent(monkeypatch, tmp_path):
    mock_stage_sonata = MagicMock(return_value=tmp_path / "circuit.json")
    mock_build_circuit = MagicMock(return_value=MagicMock())

    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.stage_sonata_from_memodel",
        mock_stage_sonata,
    )
    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging._build_memodel_circuit",
        mock_build_circuit,
    )

    mock_client = MagicMock()
    mock_memodel_entity = MagicMock()

    with patch.object(MEModelFromID, "entity", return_value=mock_memodel_entity):
        test_module.stage_memodel_as_circuit(
            client=mock_client,
            circuit=MEModelFromID(id_str="memodel-id"),
            output_dir=tmp_path / "output",
            max_concurrent=8,
        )

    assert mock_stage_sonata.call_args.kwargs["max_concurrent"] == 8


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

    mock_load_json.return_value = {"node_set": "All", "run": {"tstop": 100}}
    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.load_json", mock_load_json
    )
    # Resolve the node set via libsonata (fake) instead of reading node_id lists.
    _patch_node_set_resolution(monkeypatch, {"All": {"popA": [1, 2, 3]}}, node_set="All")

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


def test_get_simulation_parameters_symbolic_node_set(monkeypatch, tmp_path):
    """A symbolic node set (no explicit node_id list) must still be counted."""
    simulation_config_file = tmp_path / "config.json"
    mechanism_build = NeuronMechanismBuild(libnrnmech_path=_touch(tmp_path / "libnrnmech.so"))

    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.load_json",
        MagicMock(return_value={"node_set": "Excitatory", "run": {"tstop": 50}}),
    )
    # "Excitatory" resolves across two populations, 5 cells total.
    _patch_node_set_resolution(
        monkeypatch,
        {"Excitatory": {"popA": [1, 2, 3], "popB": [10, 20]}},
        node_set="Excitatory",
    )

    params = test_module.get_simulation_parameters(
        simulation_backend=SimulationBackend.bluecellulab,
        simulation_config_file=simulation_config_file,
        mechanism_build=mechanism_build,
    )

    assert params.number_of_cells == 5


def test_get_simulation_parameters_simulation_only_node_set(monkeypatch, tmp_path):
    """A node set defined only in the simulation node_sets_file (not the circuit)."""
    simulation_config_file = tmp_path / "config.json"
    mechanism_build = NeuronMechanismBuild(libnrnmech_path=_touch(tmp_path / "libnrnmech.so"))

    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.load_json",
        MagicMock(return_value={"node_set": "MySimOnlySet", "run": {"tstop": 50}}),
    )
    # "MySimOnlySet" only resolves in popA; popB has it absent (does not apply there).
    _patch_node_set_resolution(
        monkeypatch,
        {"MySimOnlySet": {"popA": [7, 8]}},
        node_set="MySimOnlySet",
        extra_populations=["popB"],
    )

    params = test_module.get_simulation_parameters(
        simulation_backend=SimulationBackend.bluecellulab,
        simulation_config_file=simulation_config_file,
        mechanism_build=mechanism_build,
    )

    assert params.number_of_cells == 2


def test_get_simulation_parameters_missing_node_set(monkeypatch, tmp_path):
    simulation_config_file = tmp_path / "config.json"
    mechanism_build = NeuronMechanismBuild(libnrnmech_path=_touch(tmp_path / "libnrnmech.so"))

    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.load_json",
        MagicMock(return_value={"node_set": "Foo", "run": {"tstop": 100}}),
    )
    _patch_node_set_resolution(monkeypatch, {"All": {"popA": [1, 2, 3]}}, node_set="Foo")

    with pytest.raises(KeyError, match="Node set 'Foo' not found"):
        test_module.get_simulation_parameters(
            simulation_backend=SimulationBackend.bluecellulab,
            simulation_config_file=simulation_config_file,
            mechanism_build=mechanism_build,
        )


def test_get_simulation_parameters_no_node_set(monkeypatch, tmp_path):
    """No node set defined in the simulation config must raise an error."""
    simulation_config_file = tmp_path / "config.json"
    mechanism_build = NeuronMechanismBuild(libnrnmech_path=_touch(tmp_path / "libnrnmech.so"))

    monkeypatch.setattr(
        "obi_one_lazy.scientific.library.simulation.neuron.staging.load_json",
        MagicMock(return_value={"run": {"tstop": 100}}),
    )
    _patch_node_set_resolution(monkeypatch, {"All": {"popA": [1, 2, 3]}}, node_set=None)

    with pytest.raises(ValueError, match="No node set defined"):
        test_module.get_simulation_parameters(
            simulation_backend=SimulationBackend.bluecellulab,
            simulation_config_file=simulation_config_file,
            mechanism_build=mechanism_build,
        )

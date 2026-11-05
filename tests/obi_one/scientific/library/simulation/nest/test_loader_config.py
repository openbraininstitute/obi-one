"""Tests for NestSonataNetwork configuration parsing (libsonata; no NEST calls)."""

import pytest

from obi_one.scientific.library.simulation.nest import constants
from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork
from obi_one.utils.io import load_json, write_json

from tests.obi_one.scientific.library.simulation.nest._circuits import write_nest_circuit


@pytest.fixture
def circuit(tmp_path):
    return write_nest_circuit(tmp_path)


def test_parses_run_from_simulation_config(circuit):
    net = NestSonataNetwork(circuit.simulation_config)
    assert net.dt == pytest.approx(0.1)
    assert net.tstop == pytest.approx(20.0)
    assert net.config["target_simulator"] == "NEST"


def test_circuit_config_with_separate_sim_config(circuit):
    net = NestSonataNetwork(circuit.circuit_config, circuit.simulation_config)
    assert net.tstop == pytest.approx(20.0)


def test_circuit_config_alone_is_rejected(circuit):
    with pytest.raises(ValueError, match="simulation config"):
        NestSonataNetwork(circuit.circuit_config)


def test_populations_parsed(circuit):
    net = NestSonataNetwork(circuit.simulation_config)
    exc = net.node_populations["exc"]
    assert exc["type"] == constants.TYPE_POINT_PROCESS
    assert exc["point_neuron_models_dir"].name == "exc"
    assert net.node_populations["input"]["type"] == constants.TYPE_VIRTUAL
    assert net.node_populations["input"]["point_neuron_models_dir"] is None
    assert net.edge_populations["exc__exc"]["type"] == constants.TYPE_CHEMICAL


def test_load_template(circuit):
    net = NestSonataNetwork(circuit.simulation_config)
    template = net.load_template("exc", "iaf_psc_alpha_type1")
    assert template["model"] == "nest:iaf_psc_alpha"
    with pytest.raises(FileNotFoundError):
        net.load_template("exc", "missing")


def test_components_default_models_dir(circuit):
    config = load_json(circuit.circuit_config)
    del config["networks"]["nodes"][0]["populations"]["exc"]["point_neuron_models_dir"]
    config["components"] = {"point_neuron_models_dir": "$BASE_DIR/model_templates/exc"}
    write_json(config, circuit.circuit_config)
    net = NestSonataNetwork(circuit.simulation_config)
    assert net.node_populations["exc"]["point_neuron_models_dir"].name == "exc"
    assert net.edge_populations["exc__exc"]["point_neuron_models_dir"].name == "exc__exc"
    assert net.load_template("exc", "iaf_psc_alpha_type1")["model"] == "nest:iaf_psc_alpha"


def test_rejects_non_nest_target(circuit):
    sim = load_json(circuit.simulation_config)
    sim["target_simulator"] = "NEURON"
    write_json(sim, circuit.simulation_config)
    with pytest.raises(ValueError, match="target_simulator"):
        NestSonataNetwork(circuit.simulation_config)


def test_rejects_unknown_population_type(circuit):
    config = load_json(circuit.circuit_config)
    config["networks"]["nodes"][0]["populations"]["exc"]["type"] = "single_compartment"
    write_json(config, circuit.circuit_config)
    with pytest.raises(ValueError, match="Unsupported node population type"):
        NestSonataNetwork(circuit.simulation_config)

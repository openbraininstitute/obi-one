"""Tests for NestSonataNetwork configuration parsing (libsonata; no NEST calls)."""

import logging

import libsonata
import nest
import pytest

from obi_one.scientific.library.simulation.nest import constants, nestml_build
from obi_one.scientific.library.simulation.nest.simulate_nest import (
    NestSonataNetwork,
    version_warnings,
)
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
    assert exc["type"] == constants.TYPE_NEST_POINT
    assert exc["point_neuron_models_dir"].name == "exc"
    assert net.node_populations["input"]["type"] == constants.TYPE_VIRTUAL
    assert net.node_populations["input"]["point_neuron_models_dir"] is None
    assert net.edge_populations["exc__exc"]["type"] == constants.TYPE_NEST_CHEMICAL


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


def test_rejects_point_process_population(circuit):
    config = load_json(circuit.circuit_config)
    config["networks"]["nodes"][0]["populations"]["exc"]["type"] = "point_process"
    write_json(config, circuit.circuit_config)
    with pytest.raises(libsonata.SonataError, match="'point_process' in a NEST circuit"):
        NestSonataNetwork(circuit.simulation_config)


def test_same_minor_version_does_not_warn():
    assert version_warnings({"nest_version": "3.10.0"}, "3.10.2") == []


def test_different_nest_minor_version_warns():
    (message,) = version_warnings({"nest_version": "3.9.0"}, "3.10.1")
    assert "NEST 3.9.0" in message
    assert "NEST 3.10.1" in message


def test_missing_nest_version_warns():
    (message,) = version_warnings({}, "3.10.0")
    assert "components.provenance.nest_version" in message


def test_different_nestml_version_warns():
    provenance = {"nest_version": "3.10.0", "nestml_version": "8.0.0"}
    (message,) = version_warnings(provenance, None, "9.0.1")
    assert "NESTML 8.0.0" in message
    assert "NESTML 9.0.1" in message


def test_missing_nestml_version_does_not_warn():
    assert version_warnings({"nest_version": "3.10.0"}, None, "9.0.1") == []


def set_provenance(circuit, provenance):
    config = load_json(circuit.circuit_config)
    config.setdefault("components", {})["provenance"] = provenance
    write_json(config, circuit.circuit_config)


def test_loader_warns_when_nest_version_differs(circuit, caplog):
    set_provenance(circuit, {"nest_version": "1.0.0"})
    with caplog.at_level(logging.WARNING):
        NestSonataNetwork(circuit.simulation_config)
    assert "NEST 1.0.0" in caplog.text


def test_loader_does_not_warn_when_nest_version_matches(circuit, caplog):
    set_provenance(circuit, {"nest_version": nest.__version__})
    with caplog.at_level(logging.WARNING):
        NestSonataNetwork(circuit.simulation_config)
    assert not caplog.text


def test_loader_warns_once_when_nestml_version_differs(circuit, caplog, monkeypatch, tmp_path):
    set_provenance(circuit, {"nest_version": nest.__version__, "nestml_version": "1.0.0"})
    net = NestSonataNetwork(circuit.simulation_config)
    (tmp_path / "custom.nestml").write_text("model custom:\n")
    monkeypatch.setattr(nestml_build, "compile_nestml_module", lambda *_: tmp_path / "lib.so")
    monkeypatch.setattr(
        NestSonataNetwork, "_nestml_model_name", staticmethod(lambda _: "iaf_psc_alpha")
    )
    with caplog.at_level(logging.WARNING):
        net._ensure_nestml_model("custom", tmp_path)
        net._ensure_nestml_model("custom", tmp_path)
    assert caplog.text.count("NESTML 1.0.0") == 1


def test_keys_that_nest_ignores_are_reported(circuit, caplog):
    config = load_json(circuit.simulation_config)
    config["conditions"] = {"celsius": 34.0}
    config["run"].update(
        {"spike_threshold": -30, "integration_method": "euler", "nsteps_block": 1000}
    )
    config["inputs"]["input_spikes"]["represents_physical_electrode"] = True
    write_json(config, circuit.simulation_config)
    with caplog.at_level(logging.WARNING):
        NestSonataNetwork(circuit.simulation_config)
    for key in ("conditions", "run.spike_threshold", "run.integration_method", "run.nsteps_block"):
        assert f"'{key}' is ignored by NEST" in caplog.text
    assert "Input 'input_spikes': 'represents_physical_electrode' is ignored" in caplog.text


def test_no_warning_without_ignored_keys(circuit, caplog):
    with caplog.at_level(logging.WARNING):
        NestSonataNetwork(circuit.simulation_config)
    assert "ignored by NEST" not in caplog.text

"""Integration tests for NestSonataNetwork.Connect / BuildNetwork (real NEST)."""

import nest
import numpy as np
import pytest

from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork
from obi_one.utils.io import write_json

from tests.obi_one.scientific.library.simulation.nest._circuits import write_nest_circuit


@pytest.fixture
def net(tmp_path) -> NestSonataNetwork:
    return NestSonataNetwork(write_nest_circuit(tmp_path).simulation_config)


def test_requires_create_before_connect(net):
    with pytest.raises(RuntimeError, match="Create"):
        net.Connect()


def test_type_level_weight_and_delay(net):
    net.BuildNetwork()
    conns = nest.GetConnections(source=net.replay_collections["input_spikes", "input"])
    assert len(conns) == 2
    assert set(conns.get("synapse_model")) == {"static_synapse"}
    assert conns.get("weight") == pytest.approx([50.0, 50.0])
    assert conns.get("delay") == pytest.approx([2.0, 2.0])


def test_per_edge_stp_overrides_template(net):
    collections = net.BuildNetwork()
    conns = nest.GetConnections(source=collections["exc"], synapse_model="tsodyks2_synapse")
    values = conns.get(["U", "u", "tau_rec", "tau_fac", "weight", "delay"])
    order = sorted(range(len(conns)), key=lambda i: values["weight"][i])

    def col(key):
        return [values[key][i] for i in order]

    assert col("weight") == pytest.approx([1.0, 2.0, 3.0])
    assert col("delay") == pytest.approx([1.5, 2.5, 3.5])
    assert col("U") == pytest.approx([0.1, 0.2, 0.3])
    assert col("u") == pytest.approx([0.1, 0.2, 0.3])
    assert col("tau_rec") == pytest.approx([100.0, 200.0, 300.0])
    assert col("tau_fac") == pytest.approx([10.0, 20.0, 30.0])


def test_delay_shorter_than_the_resolution_is_raised_to_it(tmp_path):
    circuit = write_nest_circuit(tmp_path)
    template = tmp_path / "model_templates" / "input__exc" / "static_synapse.json"
    write_json(
        {"model": "nest:static_synapse", "params": {"delay": 0.01, "weight": 50.0}}, template
    )
    net = NestSonataNetwork(circuit.simulation_config)
    net.BuildNetwork()
    conns = nest.GetConnections(source=net.replay_collections["input_spikes", "input"])
    assert conns.get("delay") == pytest.approx([0.1, 0.1])


def test_batch_spec_has_weight_and_delay_arrays_whatever_the_source():
    spec = NestSonataNetwork._batch_syn_spec(
        ({"weight": 2.0, "tau_rec": 500.0, "synapse_model": "tsodyks2_synapse"}, ["U"]),
        {"delay": np.array([0.01, 1.5, 2.5]), "U": np.array([0.1, 0.2, 0.3])},
        np.array([2, 0]),
        0.1,
    )
    assert spec["weight"].tolist() == [2.0, 2.0]
    assert spec["delay"].tolist() == [2.5, 0.1]
    assert spec["U"].tolist() == [0.3, 0.1]
    assert spec["tau_rec"] == pytest.approx(500.0)


def test_batch_spec_takes_missing_weight_and_delay_from_the_model():
    spec = NestSonataNetwork._batch_syn_spec(({}, []), {}, np.array([0, 1, 2]), 0.1)
    defaults = nest.GetDefaults("static_synapse")
    assert spec["weight"].tolist() == [defaults["weight"]] * 3
    assert spec["delay"].tolist() == [defaults["delay"]] * 3
    assert "synapse_model" not in spec


def test_receptor_type_is_connected_as_an_integer_array():
    spec = NestSonataNetwork._batch_syn_spec(
        ({}, ["receptor_type"]), {"receptor_type": np.array([1.0, 2.0])}, np.array([0, 1]), 0.1
    )
    assert spec["receptor_type"].dtype.kind == "i"

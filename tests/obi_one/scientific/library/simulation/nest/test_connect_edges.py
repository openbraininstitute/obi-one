"""Integration tests for NestSonataNetwork.Connect / BuildNetwork (real NEST)."""

import nest
import pytest

from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork

from tests.obi_one.scientific.library.simulation.nest._circuits import write_nest_circuit


@pytest.fixture
def net(tmp_path) -> NestSonataNetwork:
    return NestSonataNetwork(write_nest_circuit(tmp_path).simulation_config)


def test_requires_create_before_connect(net):
    with pytest.raises(RuntimeError, match="Create"):
        net.Connect()


def test_type_level_weight_and_delay(net):
    collections = net.BuildNetwork()
    conns = nest.GetConnections(source=collections["input"])
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

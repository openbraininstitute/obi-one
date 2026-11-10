"""Integration tests for NestSonataNetwork.Create (real NEST)."""

import pytest

from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork

from tests.obi_one.scientific.library.simulation.nest._circuits import write_nest_circuit


@pytest.fixture
def net(tmp_path) -> NestSonataNetwork:
    return NestSonataNetwork(write_nest_circuit(tmp_path).simulation_config)


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else [value]


def test_node_types_get_their_template_params(net):
    exc = net.Create()["exc"]
    assert len(exc) == 4
    assert set(_as_list(exc.get("model"))) == {"iaf_psc_alpha"}
    assert _as_list(exc.get("V_th")) == pytest.approx([-50.0, -50.0, -45.0, -45.0])
    assert _as_list(exc.get("C_m")) == pytest.approx([200.0, 200.0, 250.0, 250.0])


def test_virtual_populations_get_no_nodes(net):
    collections = net.Create()
    assert set(collections) == {"exc"}
    assert net.replay_collections == {}

"""Tests for the target semantics of ``synapse_replay`` inputs (real NEST)."""

import logging

import nest
import numpy as np
import pytest

from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork
from obi_one.utils.io import load_json, write_json

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    write_nest_circuit,
    write_spikes,
)

INPUT = "input_spikes"


@pytest.fixture
def circuit(tmp_path):
    return write_nest_circuit(tmp_path)


def set_inputs(circuit, inputs):
    config = load_json(circuit.simulation_config)
    config["inputs"] = inputs
    write_json(config, circuit.simulation_config)


def set_node_sets(circuit, node_sets):
    path = circuit.circuit_config.parent / "node_sets.json"
    write_json({**load_json(path), **node_sets}, path)


def replay_input(spike_file, node_set, delay=0.0, duration=20.0):
    return {
        "input_type": "spikes",
        "module": "synapse_replay",
        "spike_file": spike_file,
        "node_set": node_set,
        "delay": delay,
        "duration": duration,
    }


def build(circuit) -> NestSonataNetwork:
    net = NestSonataNetwork(circuit.simulation_config)
    net.BuildNetwork()
    return net


def targets_of(injectors) -> list[int]:
    return sorted(np.atleast_1d(nest.GetConnections(source=injectors).get("target")).tolist())


def exc_ids(net, node_ids) -> list[int]:
    return [net.node_collections["exc"].tolist()[i] for i in node_ids]


def test_virtual_edges_are_connected_through_the_input(circuit):
    net = build(circuit)
    injectors = net.replay_collections[INPUT, "input"]
    assert len(injectors) == 2
    assert targets_of(injectors) == exc_ids(net, [0, 2])


def test_only_targets_in_the_node_set_receive_spikes(circuit):
    set_node_sets(circuit, {"exc_first": {"population": "exc", "node_id": [0, 1]}})
    set_inputs(circuit, {INPUT: replay_input("$BASE_DIR/inputs/input_spikes.h5", "exc_first")})
    net = build(circuit)
    injectors = net.replay_collections[INPUT, "input"]
    assert len(injectors) == 1
    assert targets_of(injectors) == exc_ids(net, [0])


def test_inputs_with_different_node_sets_do_not_share_spikes(circuit):
    set_node_sets(
        circuit,
        {
            "exc_0": {"population": "exc", "node_id": [0]},
            "exc_2": {"population": "exc", "node_id": [2]},
        },
    )
    spikes = "$BASE_DIR/inputs/input_spikes.h5"
    set_inputs(circuit, {"a": replay_input(spikes, "exc_0"), "b": replay_input(spikes, "exc_2")})
    net = build(circuit)
    assert targets_of(net.replay_collections["a", "input"]) == exc_ids(net, [0])
    assert targets_of(net.replay_collections["b", "input"]) == exc_ids(net, [2])


def test_spikes_outside_the_window_are_dropped_and_the_others_are_not_shifted(circuit):
    spikes = "$BASE_DIR/inputs/input_spikes.h5"
    set_inputs(circuit, {INPUT: replay_input(spikes, "exc", delay=6.0, duration=10.0)})
    net = build(circuit)
    injectors = net.replay_collections[INPUT, "input"]
    times = {tuple(t) for t in injectors.get("spike_times")}
    assert times == {(15.0,), (7.0,)}


def test_window_end_is_exclusive(circuit):
    spikes = "$BASE_DIR/inputs/input_spikes.h5"
    set_inputs(circuit, {INPUT: replay_input(spikes, "exc", delay=5.0, duration=10.0)})
    injectors = build(circuit).replay_collections[INPUT, "input"]
    assert sorted(t for ts in injectors.get("spike_times") for t in ts) == [5.0, 7.0]


def test_input_without_spikes_in_the_window_warns_and_connects_nothing(circuit, caplog):
    spikes = "$BASE_DIR/inputs/input_spikes.h5"
    set_inputs(circuit, {INPUT: replay_input(spikes, "exc", delay=100.0, duration=10.0)})
    with caplog.at_level(logging.WARNING):
        net = build(circuit)
    assert "no spikes of 'input'" in caplog.text
    assert net.replay_collections == {}


def test_node_set_without_targets_is_an_error(circuit):
    set_inputs(circuit, {INPUT: replay_input("$BASE_DIR/inputs/input_spikes.h5", "input")})
    with pytest.raises(ValueError, match="contains no target of the edges that leave 'input'"):
        build(circuit)


def test_unknown_node_set_is_an_error(circuit):
    set_inputs(circuit, {INPUT: replay_input("$BASE_DIR/inputs/input_spikes.h5", "nowhere")})
    with pytest.raises(ValueError, match="'nowhere' is not defined"):
        build(circuit)


def test_spike_population_must_be_in_the_circuit(circuit):
    path = circuit.circuit_config.parent / "inputs" / "other.h5"
    write_spikes(path, "missing", [0], [5.0])
    set_inputs(circuit, {INPUT: replay_input("$BASE_DIR/inputs/other.h5", "exc")})
    with pytest.raises(ValueError, match="'missing' is not a node population"):
        build(circuit)


def test_spike_node_id_must_be_in_the_population(circuit):
    path = circuit.circuit_config.parent / "inputs" / "other.h5"
    write_spikes(path, "input", [0, 5], [5.0, 6.0])
    set_inputs(circuit, {INPUT: replay_input("$BASE_DIR/inputs/other.h5", "exc")})
    with pytest.raises(ValueError, match="spike node id 5 is not in population 'input'"):
        build(circuit)


def test_virtual_population_without_an_input_warns(circuit, caplog):
    set_inputs(circuit, {})
    with caplog.at_level(logging.WARNING):
        net = build(circuit)
    assert "Virtual population 'input' has no synapse_replay input" in caplog.text
    assert net.replay_collections == {}


def test_simulated_population_can_be_replayed_through_its_own_edges(circuit):
    path = circuit.circuit_config.parent / "inputs" / "exc_spikes.h5"
    write_spikes(path, "exc", [0], [5.0])
    set_inputs(circuit, {"exc_replay": replay_input("$BASE_DIR/inputs/exc_spikes.h5", "exc")})
    net = build(circuit)
    injectors = net.replay_collections["exc_replay", "exc"]
    conns = nest.GetConnections(source=injectors)
    assert targets_of(injectors) == exc_ids(net, [1])
    assert conns.get("synapse_model") == "tsodyks2_synapse"
    assert conns.get("weight") == pytest.approx(1.0)
    assert conns.get("U") == pytest.approx(0.1)
    own = nest.GetConnections(source=net.node_collections["exc"], synapse_model="tsodyks2_synapse")
    assert len(own) == 3


def test_replayed_spikes_reach_the_targets_with_the_edge_weight(tmp_path):
    circuit = write_nest_circuit(tmp_path, input_weight=5000.0)
    net = build(circuit)
    recorder = net.add_spike_recorders()["exc"]
    net.Simulate()
    senders = np.unique(recorder.get("events")["senders"]).tolist()
    assert {net.node_collections["exc"].tolist().index(s) for s in senders} >= {0, 2}

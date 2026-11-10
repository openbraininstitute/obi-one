"""Tests for the connection_overrides of the simulation config."""

import logging

import nest
import numpy as np
import pytest

from obi_one.scientific.library.simulation.nest import connection_overrides
from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork
from obi_one.utils.io import load_json, write_json

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    write_nest_circuit,
    write_spikes,
)

INPUT = "input_spikes"


def override(source="input", target="exc", **properties):
    return {"source": source, "target": target, **properties}


def network(tmp_path, overrides, input_weight=50.0, *, late_spike=False):
    """The built network; with *late_spike* the input is a single spike of node 0 at 15 ms."""
    circuit = write_nest_circuit(tmp_path, input_weight=input_weight)
    if late_spike:
        write_spikes(tmp_path / "inputs" / "input_spikes.h5", "input", [0], [15.0])
    config = load_json(circuit.simulation_config)
    config["connection_overrides"] = [{"name": f"o{i}", **o} for i, o in enumerate(overrides)]
    write_json(config, circuit.simulation_config)
    net = NestSonataNetwork(circuit.simulation_config)
    net.BuildNetwork()
    return net


def synapses(net, key=(INPUT, "input")):
    return nest.GetConnections(source=net.replay_collections[key])


def weights(synapse_collection):
    return sorted(np.atleast_1d(synapse_collection.get("weight")).tolist())


def delays(synapse_collection):
    return sorted(np.atleast_1d(synapse_collection.get("delay")).tolist())


def test_a_weight_is_a_factor_on_the_weight_of_the_circuit():
    parsed = connection_overrides.parse_overrides([override(weight=0.5)], dt=0.1)
    assert parsed[0].weight == pytest.approx(0.5)
    assert parsed[0].synapse_delay is None


def test_delay_is_a_step_and_defaults_to_the_start():
    parsed = connection_overrides.parse_overrides([override(), override(delay=2.5)], dt=0.1)
    assert [p.step for p in parsed] == [0, 25]


def test_a_delay_that_is_not_a_multiple_of_the_run_dt_is_an_error():
    with pytest.raises(ValueError, match=r"not a multiple of 0\.1 ms"):
        connection_overrides.parse_overrides([override(delay=2.55)], dt=0.1)


@pytest.mark.parametrize("field", list(connection_overrides.NEURON_ONLY))
def test_neuron_only_fields_are_errors(field):
    with pytest.raises(ValueError, match="not supported for NEST"):
        connection_overrides.parse_overrides([override(**{field: 1})], dt=0.1)


def test_a_synapse_delay_shorter_than_the_run_dt_is_raised_to_it():
    (parsed,) = connection_overrides.parse_overrides(
        [override(synapse_delay_override=0.01)], dt=0.1
    )
    assert parsed.synapse_delay == pytest.approx(0.1)


def test_overrides_are_scheduled_by_time_then_by_file_order():
    parsed = connection_overrides.parse_overrides(
        [override(delay=5), override(delay=0), override(delay=5), override(delay=99)], dt=0.5
    )
    groups = connection_overrides.schedule(parsed, last_step=100)
    assert [(step, [o.index for o in group]) for step, group in groups] == [(0, [1]), (10, [0, 2])]


def test_an_override_after_the_end_is_dropped(caplog):
    parsed = connection_overrides.parse_overrides([override(delay=30)], dt=0.1)
    with caplog.at_level(logging.WARNING):
        assert connection_overrides.schedule(parsed, last_step=100) == []
    assert "takes effect after the simulation ends" in caplog.text


def test_a_weight_scales_the_synapses_of_the_spike_replay(tmp_path):
    net = network(tmp_path, [override(weight=0.5)])
    net.Simulate()
    assert weights(synapses(net)) == pytest.approx([25.0, 25.0])


def test_overrides_scale_the_weight_of_the_circuit_and_do_not_compound(tmp_path):
    net = network(tmp_path, [override(weight=0.5), override(weight=2.0)])
    net.Simulate()
    assert weights(synapses(net)) == pytest.approx([100.0, 100.0])


def test_a_later_override_in_time_wins_over_a_listed_later_one(tmp_path):
    net = network(tmp_path, [override(weight=3.0, delay=10), override(weight=0.5)])
    net.Simulate()
    assert weights(synapses(net)) == pytest.approx([150.0, 150.0])


def test_a_weight_of_zero_disconnects_and_a_weight_of_one_restores(tmp_path):
    overrides = [override(weight=0.0, delay=5), override(weight=1.0, delay=10)]
    net = network(tmp_path, overrides)
    net.Simulate()
    assert weights(synapses(net)) == pytest.approx([50.0, 50.0])


def exc_spikes(net):
    """The times of the spikes of ``exc`` after simulating *net*."""
    recorder = net.add_spike_recorders()["exc"]
    net.Simulate()
    return np.round(recorder.get("events")["times"], 1)


def test_the_replayed_spike_drives_the_neuron_without_an_override(tmp_path):
    assert len(exc_spikes(network(tmp_path, [], input_weight=5000.0, late_spike=True))) > 0


def test_a_weight_of_zero_disconnects_before_the_spike_arrives(tmp_path):
    net = network(tmp_path, [override(weight=0.0, delay=10)], input_weight=5000.0, late_spike=True)
    assert len(exc_spikes(net)) == 0


def test_a_disconnection_after_the_spike_arrives_changes_nothing(tmp_path):
    net = network(tmp_path, [override(weight=0.0, delay=18)], input_weight=5000.0, late_spike=True)
    assert len(exc_spikes(net)) > 0


def test_a_weight_of_one_restores_the_synapse_before_the_spike(tmp_path):
    overrides = [override(weight=0.0, delay=5), override(weight=1.0, delay=14)]
    net = network(tmp_path, overrides, input_weight=5000.0, late_spike=True)
    assert len(exc_spikes(net)) > 0


def test_the_weight_stays_zero_if_it_is_not_restored(tmp_path):
    overrides = [override(weight=0.0, delay=5), override(weight=1.0, delay=16)]
    net = network(tmp_path, overrides, input_weight=5000.0, late_spike=True)
    assert len(exc_spikes(net)) == 0


def test_a_synapse_delay_replaces_the_delay_from_the_start(tmp_path):
    net = network(tmp_path, [override(synapse_delay_override=4.0)])
    net.Simulate()
    assert delays(synapses(net)) == pytest.approx([4.0, 4.0])


def test_a_synapse_delay_takes_effect_at_the_delay_of_the_override(tmp_path):
    net = network(tmp_path, [override(synapse_delay_override=4.0, delay=10)])
    net.Simulate()
    assert delays(synapses(net)) == pytest.approx([4.0, 4.0])
    only_later = network(tmp_path / "later", [override(synapse_delay_override=4.0, delay=30)])
    only_later.Simulate()
    assert delays(synapses(only_later)) == pytest.approx([2.0, 2.0])


def test_a_synapse_delay_longer_than_any_delay_of_the_circuit_is_accepted(tmp_path):
    net = network(tmp_path, [override(synapse_delay_override=15.0, delay=10)])
    net.Simulate()
    assert delays(synapses(net)) == pytest.approx([15.0, 15.0])


def test_weight_and_delay_of_one_override_act_together(tmp_path):
    net = network(tmp_path, [override(weight=0.2, synapse_delay_override=3.0, delay=5)])
    net.Simulate()
    assert weights(synapses(net)) == pytest.approx([10.0, 10.0])
    assert delays(synapses(net)) == pytest.approx([3.0, 3.0])


def test_source_and_target_select_the_synapses_between_their_nodes(tmp_path):
    net = network(tmp_path, [override(source="exc", target="exc", weight=2.0)])
    net.Simulate()
    recurrent = nest.GetConnections(
        source=net.node_collections["exc"], synapse_model="tsodyks2_synapse"
    )
    assert weights(recurrent) == pytest.approx([2.0, 4.0, 6.0])
    assert weights(synapses(net)) == pytest.approx([50.0, 50.0])


def test_the_spike_replay_of_a_simulated_population_is_reached_through_its_nodes(tmp_path):
    net = network(tmp_path, [override(source="exc", target="exc", weight=0.5)])
    net.Simulate()
    assert weights(synapses(net)) == pytest.approx([50.0, 50.0])


def test_an_override_without_synapses_only_warns(tmp_path, caplog):
    write_nest_circuit(tmp_path)
    node_sets = tmp_path / "node_sets.json"
    write_json({**load_json(node_sets), "empty": {"population": "exc", "node_id": []}}, node_sets)
    sim = tmp_path / "simulation_config.json"
    write_json(
        {
            **load_json(sim),
            "connection_overrides": [{"name": "o", **override(target="empty", weight=0.5)}],
        },
        sim,
    )
    net = NestSonataNetwork(sim)
    net.BuildNetwork()
    with caplog.at_level(logging.WARNING):
        net.Simulate()
    assert "acts on no synapse" in caplog.text


def test_the_simulation_runs_to_tstop_with_overrides(tmp_path):
    net = network(tmp_path, [override(weight=0.5, delay=7.5)])
    net.Simulate()
    assert nest.biological_time == pytest.approx(20.0)


def test_neuron_only_fields_fail_when_the_network_is_loaded(tmp_path):
    circuit = write_nest_circuit(tmp_path)
    config = load_json(circuit.simulation_config)
    config["connection_overrides"] = [{"name": "o", **override(spont_minis=0.1)}]
    write_json(config, circuit.simulation_config)
    with pytest.raises(ValueError, match="not supported for NEST"):
        NestSonataNetwork(circuit.simulation_config)

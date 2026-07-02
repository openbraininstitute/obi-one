import json
from pathlib import Path

import bluepysnap
import brian2
import brian2.devices
import brian2.units
import numpy as np
import numpy.testing as npt
import pytest

import obi_one.scientific.library.simulation.brian2.simulate_brian2 as test_module

DATA = Path(__file__).parent / "data"


@pytest.mark.parametrize(
    ("ids", "times", "expected"),
    [
        ([1, 2, 3], [10.0, 20, 30], [False, False, False]),
        ([1, 2, 3], [10.0, 20.0, 30.0], [False, False, False]),
        ([1, 2, 1], [10.0, 11.0, 50.0], [False, False, False]),
        ([1, 1, 2], [10.0, 20.0, 50.0], [False, False, False]),
        ([1, 1], [10.0, 10.5], [False, True]),
        ([2, 1, 1, 2], [5.0, 10.0, 11.0, 5.1], [False, False, True, True]),
    ],
)
def test_get_close_spikes(ids, times, expected):
    np.testing.assert_array_equal(
        test_module._get_close_spikes(np.array(ids), np.array(times), 2.0), expected
    )


def _run_simulation(tmp_path, config, *, plot=False):
    path = tmp_path / "simulation_config.json"
    with path.open("w") as fd:
        json.dump(config, fd)

    simulation = bluepysnap.Simulation(path)
    brian2.start_scope()
    brian2.devices.reinit_and_delete()

    net = test_module._build_brian2_network(simulation)

    if plot:
        statemon = brian2.StateMonitor(net.neurons[0], "v", record=True)
        net.inputs.append(statemon)

    network = brian2.Network(net.neurons, net.synapses, net.spike_monitor, *net.inputs)
    network.run(duration=simulation.run.tstop * brian2.units.ms)

    if plot:
        import matplotlib.pyplot as plt  # noqa: PLC0415

        plt.figure(figsize=(9, 4))
        plt.plot(statemon.t / brian2.units.ms, statemon.v[0] / brian2.units.mV, c="r")
        plt.plot(statemon.t / brian2.units.ms, statemon.v[1] / brian2.units.mV, c="g")
        plt.plot(statemon.t / brian2.units.ms, statemon.v[2] / brian2.units.mV, c="b")
        # plot(spikemon.t/ms, spikemon.v/mV, 'ob')
        plt.xlabel("Time (ms)")
        plt.ylabel("v (mV)")
        plt.savefig("test.png")

    return net.spike_monitor


def test_no_stim_or_report(tmp_path):
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
    }
    spike_monitor = _run_simulation(tmp_path, config)
    spikes = dict(spike_monitor.spike_trains().items())
    for i in range(3):
        assert not spikes[i].any()


def test_spike_replay(tmp_path):
    timestamps = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    path = test_module._write_spikes(
        tmp_path / "spikes.h5",
        population_name="drosophila",
        timestamps=timestamps,
        node_ids=tuple([0] * len(timestamps)),
    )
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "replay": {
                "input_type": "spikes",
                "module": "synapse_replay",
                "delay": 0.0,
                "duration": 400.0,
                "spike_file": str(path),
                "node_set": "All",
            },
        },
    }

    spike_monitor = _run_simulation(tmp_path, config, plot=True)
    spikes = dict(spike_monitor.spike_trains().items())
    assert len(spikes[0]) == 0
    npt.assert_allclose(spikes[1], np.array([0.9]) * brian2.units.msecond)
    assert spikes[1] == spikes[2]

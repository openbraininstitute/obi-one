"""Tests for brian2 simulator

* using a synthetic `drosophila` model, 3 neurons, w/ all to all connectivity
* see `tests/obi_one/scientific/library/simulation/data/create_data.py`
* model is a simple exponential decay, where spikes cause an increase of `w` to the voltage
"""

import copy
import json
from pathlib import Path

import bluepysnap
import brian2
import brian2.units
import libsonata
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


def _run_simulation(
    tmp_path, config, *, plot_voltage: bool = False
) -> tuple[bluepysnap.Simulation, test_module.Brian2Network]:
    if plot_voltage:
        if "reports" in config:
            reports = config["reports"]
        else:
            reports = config["reports"] = {}

        reports["test_plot"] = {
            "sections": "soma",
            "type": "compartment",
            "variable_name": "v",
            "unit": "mV",
            "dt": config["run"]["dt"],
            "start_time": 0,
            "end_time": config["run"]["tstop"],
        }

    path = tmp_path / "simulation_config.json"
    with path.open("w") as fd:
        json.dump(config, fd)

    net = test_module.run_sonata_brian2_trial(path)

    sim_config = bluepysnap.Simulation(path)

    if plot_voltage:
        import matplotlib.pyplot as plt  # noqa: PLC0415

        sim_config.reports["test_plot"].filter().trace(plot_type="all")
        plt.savefig("test.png")

    return sim_config, net


def test_no_stim_or_report(tmp_path):
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
    }
    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    for i in range(3):
        assert not spikes[i].any()


def test_spike_replay(tmp_path):
    timestamps = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1)
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

    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    assert len(spikes[0]) == 0
    npt.assert_allclose(spikes[1], np.array([0.9]) * brian2.units.msecond)
    assert spikes[1] == spikes[2]

    # limit duration, should have no spikes
    config["inputs"]["replay"]["duration"] = 0.1
    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    for i in range(3):
        assert not spikes[i].any()

    # delay spike start until there wouldn't be enough to fire
    config["inputs"]["replay"]["duration"] = 400
    config["inputs"]["replay"]["delay"] = 1.9
    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    for i in range(3):
        assert not spikes[i].any()

    # run sim for longer, should spike now
    config["run"]["tstop"] = 4
    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    assert len(spikes[0]) == 0
    # 1.9 since delayed by 1.9, 0.3 since the voltage has decayed in the meantime,
    # so it needs another 3 dts
    npt.assert_allclose(spikes[1], np.array([1.9 + 0.3 + 0.9]) * brian2.units.msecond)
    assert spikes[1] == spikes[2]


def test_poisson(tmp_path):
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "poisson": {
                "input_type": "spikes",
                "module": "poisson",
                "node_set": "0",
                "delay": 0,
                "duration": 1000,
                "rate": 150,
                "weight": 68.75,
            }
        },
    }
    _, net = _run_simulation(tmp_path, config)
    assert len(net.inputs) == 1
    assert isinstance(net.inputs[0], brian2.PoissonInput)


def test_current_stim(tmp_path):
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "linear": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 3000,
                "delay": 0.1,
                "duration": 4,
                "node_set": "0",
            }
        },
    }

    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    assert len(spikes[0]) == 1
    assert 0 == len(spikes[1]) == len(spikes[2])


def test_current_stim_groupby(tmp_path):
    # current stims with the same target node_set will have their currents summed
    # this assumes the dt is constant, but this is true since they are compared to the simulation dt
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "linear": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 3000,
                "node_set": "0",
                "delay": 0,
                "duration": 4,
            }
        },
    }

    spikes0 = dict(_run_simulation(tmp_path, config)[1].spike_monitor.spike_trains().items())

    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "linear0": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 1500,
                "node_set": "0",
                "delay": 0,
                "duration": 4,
            },
            "linear1": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 1500,
                "node_set": "0",
                "delay": 0,
                "duration": 4,
            },
        },
    }
    spikes1 = dict(_run_simulation(tmp_path, config)[1].spike_monitor.spike_trains().items())

    assert len(spikes0[0]) == 1 == len(spikes1[0])
    npt.assert_equal(spikes0[0], spikes1[0])
    assert 0 == len(spikes0[1]) == len(spikes0[2])
    assert 0 == len(spikes1[1]) == len(spikes1[2])


def test_linear_current_stim():
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "linear": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 0,
                "amp_end": 4,
                "delay": 0,
                "duration": 4,
                "node_set": "0",
            }
        },
    }

    sc = libsonata.SimulationConfig(json.dumps(config), ".")
    t = test_module.Linear(sc.input("linear"))
    res = t._get_currents(dt=1, simulation_length=5)
    npt.assert_array_equal(res, [0.0, 1.0, 2.0, 3.0, 4.0, 0.0])

    config["inputs"]["linear"]["delay"] = 1
    sc = libsonata.SimulationConfig(json.dumps(config), ".")
    t = test_module._create_input(sc.input("linear"))
    res = t._get_currents(dt=1, simulation_length=5)
    npt.assert_array_equal(res, [0.0, 0.0, 1.0, 2.0, 3.0, 4.0])


@pytest.mark.parametrize(
    ("delay", "width", "frequency", "duration", "expected"),
    [
        (0, 0.2, 2, 2, [1, 1, 0, 0, 0, 1, 1, 0, 0, 0, 1]),
        (0.1, 0.2, 2, 2, [0, 1, 1, 0, 0, 0, 1, 1, 0, 0, 0]),
        (0.4, 0.2, 2, 2, [0, 0, 0, 0, 1, 1, 0, 0, 0, 1, 1]),
        (0.3, 0.2, 0.5, 2, [0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0]),
        (0, 0.1, 2, 2, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
        (0, 0.1, 2, 0.5, [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
    ],
)
def test_pulse_current_stim(delay, width, frequency, duration, expected):
    config = {
        "run": {"tstop": 1, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "pulse": {
                "input_type": "current_clamp",
                "module": "pulse",
                "frequency": frequency,
                "amp_start": 1,
                "width": width,
                "delay": delay,
                "duration": duration,
                "node_set": "sugar",
            },
        },
    }
    sc = libsonata.SimulationConfig(json.dumps(config), ".")
    t = test_module._create_input(sc.input("pulse"))
    res = t._get_currents(dt=config["run"]["dt"], simulation_length=config["run"]["tstop"])
    npt.assert_array_equal(res, expected)


@pytest.mark.parametrize(
    ("delay", "frequency", "duration", "expected"),
    [
        (0, 1, 2, [0, 1, 0, -1, 0, 1, 0, -1, 0]),
        (0.25, 1, 2, [0, 0, 1, 0, -1, 0, 1, 0, -1]),
        (0, 1, 1, [0, 1, 0, -1, 0, 0, 0, 0, 0]),
        (0.25, 1, 0.5, [0, 0, 1, 0, 0, 0, 0, 0, 0]),
    ],
)
def test_sinusoidal_current_stim(delay, frequency, duration, expected):
    config = {
        "run": {"tstop": 2, "dt": 0.25, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "sinusoidal": {
                "input_type": "current_clamp",
                "module": "sinusoidal",
                "frequency": frequency,
                "amp_start": 1,
                "dt": 0.25,
                "delay": delay,
                "duration": duration,
                "node_set": "Mosaic",
            },
        },
    }
    sc = libsonata.SimulationConfig(json.dumps(config), ".")
    t = test_module._create_input(sc.input("sinusoidal"))
    res = t._get_currents(dt=config["run"]["dt"], simulation_length=config["run"]["tstop"])
    npt.assert_almost_equal(res, expected)


def test_current_stim_report(tmp_path):
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "linear": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 3000,
                "delay": 0.1,
                "duration": 4,
                "node_set": "0",
            }
        },
        "reports": {
            "soma0": {
                "sections": "soma",
                "type": "compartment",
                "variable_name": "v",
                "unit": "mV",
                "dt": 0.1,
                "start_time": 0,
                "end_time": 5,
            },
            "soma1": {
                "sections": "soma",
                "type": "compartment",
                "variable_name": "v",
                "unit": "mV",
                "dt": 0.1,
                "start_time": 0,
                "end_time": 5,
                "cells": "0",
            },
        },
    }
    simulation, _ = _run_simulation(tmp_path, config)
    soma0 = simulation.reports["soma0"].filter().report.copy()
    assert soma0.shape == (20, 3)
    assert (soma0.iloc[0] == [500, 500, 500]).all()  # all cells start at 500mv
    assert np.all(soma0.iloc[1] == soma0.iloc[1].iloc[0])  # no stimulus yet, all remain the same
    assert soma0.iloc[2].iloc[0] != soma0.iloc[2].iloc[1]  # 0 is being stimulated
    assert soma0.iloc[2].iloc[1] == soma0.iloc[2].iloc[2]

    # record a nodeset of a single cell
    soma1 = simulation.reports["soma1"].filter().report.copy()
    assert soma1.shape == (20, 1)
    npt.assert_allclose(soma1["drosophila", 0], soma0["drosophila", 0])


def test_current_stim_report_failure(tmp_path):
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "reports": {
            "soma0": {
                "sections": "soma",
                "type": "compartment",
                "variable_name": "v",
                "unit": "mV",
                "dt": 0.1,
                "start_time": 0,
                "end_time": 5,
            },
        },
    }

    c = copy.deepcopy(config)
    c["reports"]["soma0"]["sections"] = "all"
    with pytest.raises(TypeError):
        _run_simulation(tmp_path, c)

    c = copy.deepcopy(config)
    c["reports"]["soma0"]["variable_name"] = "i"
    with pytest.raises(RuntimeError):
        _run_simulation(tmp_path, c)

    c = copy.deepcopy(config)
    c["reports"]["soma0"]["dt"] = 1
    with pytest.raises(RuntimeError):
        _run_simulation(tmp_path, c)

    c = copy.deepcopy(config)
    c["reports"]["soma0"]["enabled"] = False
    _run_simulation(tmp_path, c)


def test_connection_override(tmp_path):
    config = {
        "run": {"tstop": 2, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            # will cause spikes in `0`, which will make 1 & 2 spike, normally...
            "linear": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 12000,
                "delay": 0,
                "duration": 4,
                "node_set": "0",
            },
        },
        "connection_overrides": [
            # ...but disconnect 0 from other neurons
            {"name": "Disconnect0", "source": "0", "target": "All", "delay": 0.0, "weight": 0.0}
        ],
    }
    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    assert not spikes[1].any()
    assert not spikes[2].any()

    config["connection_overrides"] = [
        {
            # ... or unless the synapse delay is too large
            "name": "ChangeSynapseDelay",
            "source": "0",
            "target": "All",
            "delay": 0.0,
            "synapse_delay_override": 2.0,
        }
    ]
    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())
    assert not spikes[1].any()
    assert not spikes[2].any()


def test_connection_override_mid_simulation(tmp_path):
    delay = 1.5
    config = {
        "run": {"tstop": 4, "dt": 0.1, "random_seed": 42},
        "target_simulator": "Brian2",
        "network": str(DATA / "circuit_config.json"),
        "inputs": {
            "linear": {
                "input_type": "current_clamp",
                "module": "linear",
                "amp_start": 12000,
                "delay": 0,
                "duration": 4,
                "node_set": "0",
            },
        },
        "connection_overrides": [
            {
                "name": "DelayedDisconnect",
                "source": "0",
                "target": "All",
                "delay": delay,
                "weight": 0.0,
            }
        ],
    }
    spike_monitor = _run_simulation(tmp_path, config)[1].spike_monitor
    spikes = dict(spike_monitor.spike_trains().items())

    # Neurons 1&2 should spike BEFORE the override
    delay *= brian2.units.ms
    assert any(t < delay for t in spikes[1])
    assert any(t < delay for t in spikes[2])

    # But no spikes AFTER the override
    assert not any(t > delay for t in spikes[1])
    assert not any(t > delay for t in spikes[2])

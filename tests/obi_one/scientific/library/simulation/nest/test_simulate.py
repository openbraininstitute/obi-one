"""End-to-end tests: build -> simulate (real NEST)."""

import h5py
import nest
import numpy as np
import pytest

from obi_one.scientific.library.simulation.nest.simulate_nest import (
    NestSonataNetwork,
    run_simulation,
)
from obi_one.utils.io import load_json, write_json

from tests.obi_one.scientific.library.simulation.nest._circuits import write_nest_circuit


def test_replayed_spikes_drive_neurons(tmp_path):
    result = write_nest_circuit(tmp_path, input_weight=5000.0)

    network = NestSonataNetwork(result.simulation_config)
    network.BuildNetwork()
    recorder = network.add_spike_recorders()["exc"]
    network.Simulate()
    assert nest.biological_time == pytest.approx(20.0)
    events = recorder.get("events")
    exc_ids = network.node_collections["exc"].tolist()
    fired = {exc_ids.index(s) for s in events["senders"]}
    assert fired >= {0, 2}


def test_simulate_requires_build(tmp_path):
    result = write_nest_circuit(tmp_path)
    with pytest.raises(RuntimeError, match="built"):
        NestSonataNetwork(result.simulation_config).Simulate()


def test_run_simulation_writes_sonata_spike_report(tmp_path):
    result = write_nest_circuit(tmp_path, input_weight=5000.0)

    report = run_simulation(result.simulation_config)

    assert report.exists()
    with h5py.File(report, "r") as handle:
        spikes = handle["spikes"]
        assert set(spikes) == {"exc"}
        group = spikes["exc"]
        timestamps = group["timestamps"][:]
        node_ids = group["node_ids"][:]
        assert node_ids.dtype == np.uint64
        assert len(timestamps) == len(node_ids)
        assert len(timestamps) > 0
        assert np.all(np.diff(timestamps) >= 0)
        assert {0, 2} <= set(node_ids.tolist())


def test_run_simulation_rejects_voltage_reports(tmp_path):
    result = write_nest_circuit(tmp_path)
    sim_config = result.simulation_config
    data = load_json(sim_config)
    data["reports"] = {
        "soma_v": {
            "cells": "exc",
            "variable_name": "v",
            "sections": "soma",
            "type": "compartment",
            "dt": 0.1,
            "start_time": 0.0,
            "end_time": 20.0,
        }
    }
    write_json(data, sim_config)

    with pytest.raises(NotImplementedError, match="eports"):
        run_simulation(sim_config)

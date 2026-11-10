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

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    read_soma_report,
    write_nest_circuit,
)


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

    report = run_simulation(result.simulation_config).spike_report_file

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


def test_run_simulation_writes_a_soma_report_that_libsonata_reads(tmp_path):
    result = write_nest_circuit(tmp_path)
    data = load_json(result.simulation_config)
    data["output"] = {"output_dir": "$BASE_DIR/out", "spikes_file": "spikes.h5"}
    data["reports"] = {
        "soma_v": {
            "cells": "exc",
            "variable_name": "v",
            "sections": "soma",
            "type": "compartment",
            "dt": 0.5,
            "start_time": 0.0,
            "end_time": 20.0,
        }
    }
    write_json(data, result.simulation_config)

    results = run_simulation(result.simulation_config)

    assert results.voltage_report_files == [tmp_path / "out" / "soma_v.h5"]
    ids, times, values = read_soma_report(results.voltage_report_files[0], "exc")
    assert ids.tolist() == [0, 1, 2, 3]
    assert times == pytest.approx(np.arange(0.0, 20.0, 0.5))
    assert values.shape == (40, 4)
    assert np.isfinite(values).all()


def test_kernel_runs_on_the_requested_threads(tmp_path):
    result = write_nest_circuit(tmp_path)

    NestSonataNetwork(result.simulation_config).Create()
    assert nest.local_num_threads == 1

    NestSonataNetwork(result.simulation_config, num_threads=4).Create()
    assert nest.local_num_threads == 4
    assert nest.total_num_virtual_procs == 4


def test_threads_must_be_positive(tmp_path):
    result = write_nest_circuit(tmp_path)
    with pytest.raises(ValueError, match="num_threads"):
        NestSonataNetwork(result.simulation_config, num_threads=0)


def test_spike_report_does_not_depend_on_the_thread_count(tmp_path):
    reports = {}
    for threads in (1, 4):
        result = write_nest_circuit(tmp_path / str(threads), input_weight=5000.0)
        report = run_simulation(result.simulation_config, num_threads=threads).spike_report_file
        assert nest.local_num_threads == threads
        with h5py.File(report, "r") as handle:
            reports[threads] = (
                handle["spikes/exc/timestamps"][:].tolist(),
                handle["spikes/exc/node_ids"][:].tolist(),
            )

    assert reports[1][0]
    assert reports[1] == reports[4]


def _set_run(simulation_config, **values):
    data = load_json(simulation_config)
    data["run"].update(values)
    write_json(data, simulation_config)


def _stochastic_spikes(root, seed):
    """Spikes of ``exc`` in a circuit of ``pp_psc_delta`` neurons, whose firing is random."""
    result = write_nest_circuit(root, input_weight=5000.0)
    for name in ("iaf_psc_alpha_type1", "iaf_psc_alpha_type2"):
        write_json(
            {
                "model": "nest:pp_psc_delta",
                "params": {"c_1": 5.0, "c_2": 0.0, "c_3": 1.0, "dead_time": 1.0},
            },
            root / "model_templates" / "exc" / f"{name}.json",
        )
    _set_run(result.simulation_config, random_seed=seed, tstop=200.0)
    report = run_simulation(result.simulation_config).spike_report_file
    with h5py.File(report, "r") as handle:
        group = handle["spikes/exc"]
        return group["timestamps"][:].tolist(), group["node_ids"][:].tolist()


@pytest.mark.parametrize(("random_seed", "expected"), [(0, 1), (41, 42)])
def test_kernel_is_seeded_from_the_run_config(tmp_path, random_seed, expected):
    """NEST rejects a seed of 0, so the config seed is shifted by one."""
    result = write_nest_circuit(tmp_path)
    _set_run(result.simulation_config, random_seed=random_seed)

    NestSonataNetwork(result.simulation_config).Create()

    assert nest.rng_seed == expected


def test_negative_seed_is_rejected(tmp_path):
    result = write_nest_circuit(tmp_path)
    _set_run(result.simulation_config, random_seed=-1)
    with pytest.raises(ValueError, match="random_seed"):
        NestSonataNetwork(result.simulation_config)


def test_random_models_repeat_with_the_same_seed(tmp_path):
    first = _stochastic_spikes(tmp_path / "a", seed=0)
    again = _stochastic_spikes(tmp_path / "b", seed=0)
    other = _stochastic_spikes(tmp_path / "c", seed=1)

    assert first[0]
    assert first == again
    assert first != other


def edit_template(circuit, population, name, edit):
    path = circuit.circuit_config.parent / "model_templates" / population / f"{name}.json"
    template = load_json(path)
    edit(template)
    write_json(template, path)


def test_unknown_node_parameter_is_reported_with_model_and_template(tmp_path):
    result = write_nest_circuit(tmp_path)
    edit_template(result, "exc", "iaf_psc_alpha_type1", lambda t: t["params"].update({"C_mm": 1.0}))

    with pytest.raises(ValueError, match="'exc': template 'iaf_psc_alpha_type1'") as error:
        NestSonataNetwork(result.simulation_config).BuildNetwork()
    assert "['C_mm']" in str(error.value)
    assert "'iaf_psc_alpha'" in str(error.value)
    assert "'C_m'" in str(error.value)


def test_unknown_edge_parameter_is_reported(tmp_path):
    result = write_nest_circuit(tmp_path)
    edit_template(
        result,
        "input__exc",
        "static_synapse",
        lambda t: t.setdefault("params", {}).update({"U": 0.5}),
    )

    with pytest.raises(ValueError, match=r"template 'static_synapse'.*\['U'\]"):
        NestSonataNetwork(result.simulation_config).BuildNetwork()


def test_unknown_dynamics_parameter_is_reported(tmp_path):
    result = write_nest_circuit(tmp_path)
    edit_template(
        result,
        "exc__exc",
        "tsodyks2_synapse",
        lambda t: t["dynamics_params"].update({"tau_recc": "ms"}),
    )

    with pytest.raises(ValueError, match=r"\['tau_recc'\]"):
        NestSonataNetwork(result.simulation_config).BuildNetwork()


def test_parameters_of_the_model_are_accepted(tmp_path):
    result = write_nest_circuit(tmp_path)

    network = NestSonataNetwork(result.simulation_config)
    network.BuildNetwork()
    assert nest.network_size > 0

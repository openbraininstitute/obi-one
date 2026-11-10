"""Tests for the current clamp inputs: waveforms (pure) and their effect in NEST."""

import logging

import nest
import numpy as np
import pytest

from obi_one.scientific.library.simulation.nest import current_clamps
from obi_one.scientific.library.simulation.nest.simulate_nest import NestSonataNetwork
from obi_one.utils.io import load_json, write_json

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    read_soma_report,
    write_cells_circuit,
    write_nest_circuit,
)

DT = 0.1
TSTOP = 60.0
FRAMES = {"type": "compartment", "variable_name": "v", "dt": DT, "start_time": 0, "end_time": TSTOP}


def clamp(module, node_set="cells", delay=10.0, duration=20.0, **properties):
    return {
        "input_type": "current_clamp",
        "module": module,
        "node_set": node_set,
        "delay": delay,
        "duration": duration,
        **properties,
    }


def simulate(tmp_path, inputs, n=2):
    """The ``(nodes, frames)`` potentials that NEST gives to quiet neurons driven by *inputs*."""
    circuit = write_cells_circuit(
        tmp_path, n=n, tstop=TSTOP, sections={"inputs": inputs, "reports": {"soma": FRAMES}}
    )
    network = NestSonataNetwork(circuit.simulation_config)
    network.BuildNetwork()
    network.add_report_recorders()
    network.Simulate()
    (path,) = network.write_reports()
    return read_soma_report(path, "cells")[2].T


def reference(current):
    """The potentials of a neuron that gets ``current(t)`` pA in the step that starts at t."""
    nest.ResetKernel()
    nest.resolution = DT
    neuron = nest.Create("iaf_psc_alpha")
    multimeter = nest.Create("multimeter", params={"record_from": ["V_m"], "interval": DT})
    nest.Connect(multimeter, neuron, syn_spec={"delay": DT})
    for step in range(round(TSTOP / DT)):
        neuron.set(I_e=float(current(step * DT)))
        nest.Simulate(DT)
    return np.concatenate([[-70.0], multimeter.get("events")["V_m"]])[: round(TSTOP / DT)]


def test_a_constant_current_is_zero_outside_its_window(tmp_path):
    traces = simulate(tmp_path, {"c": clamp("linear", amp_start=0.1)})
    expected = reference(lambda t: 100.0 if 10.0 <= t < 30.0 - 1e-9 else 0.0)
    assert traces[0] == pytest.approx(expected, abs=1e-4)
    assert traces[1] == pytest.approx(expected, abs=1e-4)


def test_a_ramp_goes_from_amp_start_to_amp_end(tmp_path):
    traces = simulate(tmp_path, {"c": clamp("linear", amp_start=0.05, amp_end=0.25)})

    def current(t):
        return (50.0 + 200.0 * (t - 10.0) / 20.0) if 10.0 <= t < 30.0 - 1e-9 else 0.0

    assert traces[0] == pytest.approx(reference(current), abs=1e-4)


def test_pulses_repeat_at_the_frequency_and_the_last_is_cut(tmp_path):
    inputs = {"c": clamp("pulse", delay=5.0, duration=27.0, amp_start=0.1, width=4.0, frequency=50)}

    def current(t):
        inside = 5.0 <= t < 32.0 - 1e-9
        return 100.0 if inside and ((t - 5.0 + 1e-9) % 20.0) < 4.0 else 0.0

    assert simulate(tmp_path, inputs)[0] == pytest.approx(reference(current), abs=1e-4)


def test_a_sinusoid_starts_at_phase_zero_at_its_delay(tmp_path):
    inputs = {"c": clamp("sinusoidal", delay=10.0, duration=30.0, amp_start=0.1, frequency=50.0)}

    def current(t):
        inside = 10.0 <= t < 40.0 - 1e-9
        return 100.0 * np.sin(2 * np.pi * 50.0 * (t - 10.0) / 1000.0) if inside else 0.0

    assert simulate(tmp_path, inputs)[0] == pytest.approx(reference(current), abs=1e-4)


def test_currents_that_act_on_a_node_add_up(tmp_path):
    inputs = {
        "a": clamp("linear", amp_start=0.04),
        "b": clamp("linear", delay=20.0, amp_start=0.06),
    }
    expected = reference(
        lambda t: (
            (40.0 if 10.0 <= t < 30.0 - 1e-9 else 0.0) + (60.0 if 20.0 <= t < 40.0 - 1e-9 else 0.0)
        )
    )
    assert simulate(tmp_path, inputs)[0] == pytest.approx(expected, abs=1e-4)


def test_only_the_nodes_of_the_node_set_get_current(tmp_path):
    traces = simulate(tmp_path, {"c": clamp("linear", node_set="first", amp_start=0.1)})
    assert traces[1] == pytest.approx(np.full(traces.shape[1], -70.0))
    assert traces[0].max() > -70.0


def test_a_window_that_starts_before_the_second_step_starts_at_it(tmp_path):
    traces = simulate(tmp_path, {"c": clamp("linear", delay=0.0, duration=10.0, amp_start=0.1)})
    expected = reference(lambda t: 100.0 if 0.2 - 1e-9 <= t < 10.0 - 1e-9 else 0.0)
    assert traces[0] == pytest.approx(expected, abs=1e-4)


def test_a_negative_amplitude_hyperpolarizes(tmp_path):
    assert simulate(tmp_path, {"c": clamp("linear", amp_start=-0.1)})[0].min() < -70.0


def test_a_node_set_without_nodes_is_an_error(tmp_path):
    circuit = write_cells_circuit(
        tmp_path, sections={"inputs": {"c": clamp("linear", node_set="nobody", amp_start=0.1)}}
    )
    network = NestSonataNetwork(circuit.simulation_config)
    with pytest.raises(ValueError, match="not defined"):
        network.BuildNetwork()


def test_a_node_set_that_selects_no_nest_point_node_is_an_error(tmp_path):
    write_nest_circuit(tmp_path)
    simulation = tmp_path / "simulation_config.json"
    config = load_json(simulation)
    config["inputs"] = {"c": clamp("linear", node_set="input", amp_start=0.1)}
    write_json(config, simulation)
    network = NestSonataNetwork(simulation)
    with pytest.raises(ValueError, match="contains no nest_point node"):
        network.BuildNetwork()


def test_a_pulse_longer_than_its_period_is_an_error(tmp_path):
    inputs = {"c": clamp("pulse", amp_start=0.1, width=30.0, frequency=50)}
    network = NestSonataNetwork(
        write_cells_circuit(tmp_path, sections={"inputs": inputs}).simulation_config
    )
    with pytest.raises(ValueError, match="longer than the period"):
        network.BuildNetwork()


def test_other_modules_are_not_supported(tmp_path):
    inputs = {"c": clamp("noise", mean_percent=1.0, variance=0.1)}
    network = NestSonataNetwork(
        write_cells_circuit(tmp_path, sections={"inputs": inputs}).simulation_config
    )
    with pytest.raises(NotImplementedError, match="'linear', 'pulse', 'sinusoidal'"):
        network.BuildNetwork()


def test_an_empty_window_only_warns(tmp_path, caplog):
    inputs = {"c": clamp("linear", delay=10.0, duration=0.0, amp_start=0.1)}
    network = NestSonataNetwork(
        write_cells_circuit(tmp_path, sections={"inputs": inputs}).simulation_config
    )
    with caplog.at_level(logging.WARNING):
        network.BuildNetwork()
    assert "its window contains no step" in caplog.text


def test_the_generators_are_kept_by_input_name(tmp_path):
    inputs = {
        "a": clamp("linear", amp_start=0.1),
        "b": clamp("sinusoidal", amp_start=0.1, frequency=10),
    }
    network = NestSonataNetwork(
        write_cells_circuit(tmp_path, sections={"inputs": inputs}).simulation_config
    )
    network.BuildNetwork()
    assert {k: v.get("model") for k, v in network._current_generators.items()} == {
        "a": "dc_generator",
        "b": "ac_generator",
    }


def test_window_rounds_to_steps_and_starts_at_the_second_step():
    window = current_clamps.Window.of(delay=10.04, duration=19.96, dt=DT)
    assert (window.start, window.end) == (100, 300)
    early = current_clamps.Window.of(delay=0.0, duration=5.0, dt=DT)
    assert (early.start, early.end, early.anchor) == (2, 50, 0.0)
    assert current_clamps.Window.of(delay=0.0, duration=0.1, dt=DT).is_empty


def test_ramp_steps_interpolate_to_the_step_before_the_end():
    window = current_clamps.Window(start=10, end=14, anchor=1.0)
    steps = current_clamps.linear_steps(0.0, 0.4, window)
    assert sorted(steps) == [10, 11, 12, 13, 14]
    assert [steps[k] for k in sorted(steps)] == pytest.approx([0.0, 100.0, 200.0, 300.0, 0.0])


def pulses(width, window_end, frequency=500):
    window = current_clamps.Window(start=10, end=window_end, anchor=1.0)
    return current_clamps.pulse_steps(0.1, width, frequency, delay=1.0, window=window, dt=DT)


def test_pulses_start_every_period_from_the_delay():
    steps = pulses(width=0.5, window_end=60)
    assert steps == {10: 100.0, 15: 0.0, 30: 100.0, 35: 0.0, 50: 100.0, 55: 0.0, 60: 0.0}


def test_the_last_pulse_is_cut_at_the_window_end():
    steps = pulses(width=1.5, window_end=60)
    assert steps[50] == pytest.approx(100.0)
    assert steps[60] == pytest.approx(0.0)
    assert 65 not in steps


def test_back_to_back_pulses_keep_the_current_between_them():
    steps = pulses(width=2.0, window_end=50)
    assert steps == {10: 100.0, 30: 100.0, 50: 0.0}


def test_step_times_are_one_step_before_their_current_acts():
    params = current_clamps.step_current({2: 100.0, 5: 0.0}, DT)
    assert params == {"amplitude_times": [0.1, 0.4], "amplitude_values": [100.0, 0.0]}


def test_sinusoid_phase_is_measured_from_the_delay():
    window = current_clamps.Window.of(delay=10.0, duration=20.0, dt=DT)
    params = current_clamps.sinusoidal_parameters(0.1, 50.0, window, DT)
    assert params["amplitude"] == pytest.approx(100.0)
    assert params["phase"] == pytest.approx((360.0 * 50.0 * (DT - 10.0) / 1000.0) % 360.0)
    assert (params["start"], params["stop"]) == (pytest.approx(9.9), pytest.approx(29.9))

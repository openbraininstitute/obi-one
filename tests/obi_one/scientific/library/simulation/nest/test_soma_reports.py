"""Tests for the SONATA soma reports of the membrane potential (real NEST)."""

import h5py
import numpy as np
import pytest

from obi_one.scientific.library.simulation.nest import soma_reports
from obi_one.scientific.library.simulation.nest.simulate_nest import (
    NestSonataNetwork,
    run_simulation,
)

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    read_soma_report,
    write_cells_circuit,
)

RUN_DT = 0.1
SOMA = {"type": "compartment", "variable_name": "v"}


def potential(t):
    """V_m of an iaf_psc_alpha at rest (-70 mV) driven by 100 pA: R * I = 4 mV, tau_m = 10 ms."""
    return -70.0 + 4.0 * (1.0 - np.exp(-np.asarray(t) / 10.0))


def report(**kwargs):
    return {"dt": 1.0, "start_time": 0.0, "end_time": 50.0, **SOMA, **kwargs}


def run(tmp_path, reports, n=2, tstop=50.0, **kwargs):
    circuit = write_cells_circuit(
        tmp_path, params={"I_e": 100.0}, n=n, tstop=tstop, sections={"reports": reports}, **kwargs
    )
    network = NestSonataNetwork(circuit.simulation_config)
    network.BuildNetwork()
    network.add_report_recorders()
    network.Simulate()
    return circuit, network.write_reports()


def test_frames_have_the_membrane_potential_at_their_times(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(start_time=5.0, end_time=20.0)})
    ids, times, data = read_soma_report(path, "cells")
    assert ids.tolist() == [0, 1]
    assert times == pytest.approx(np.arange(5.0, 20.0, 1.0))
    assert data == pytest.approx(np.tile(potential(times)[:, None], 2), abs=1e-4)


def test_first_frame_at_zero_is_the_potential_before_the_first_step(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(end_time=5.0)})
    _, times, data = read_soma_report(path, "cells")
    assert times == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])
    assert data[0] == pytest.approx([-70.0, -70.0])
    assert data[:, 0] == pytest.approx(potential(times), abs=1e-4)


def test_report_dt_is_a_multiple_of_the_run_dt(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(dt=0.5, start_time=1.0, end_time=3.0)})
    _, times, data = read_soma_report(path, "cells")
    assert times == pytest.approx([1.0, 1.5, 2.0, 2.5])
    assert data[:, 0] == pytest.approx(potential(times), abs=1e-4)


def test_frames_every_run_step_reach_the_last_step_before_the_end(tmp_path):
    _, (path,) = run(
        tmp_path, {"soma": report(dt=RUN_DT, start_time=0.0, end_time=50.0)}, tstop=50.0
    )
    _, times, data = read_soma_report(path, "cells")
    assert len(times) == 500
    assert times[-1] == pytest.approx(49.9)
    assert data[-1, 0] == pytest.approx(potential(49.9), abs=1e-4)


def test_a_report_dt_below_the_run_dt_is_raised_to_it(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(dt=0.01, end_time=1.0)})
    assert read_soma_report(path, "cells")[1] == pytest.approx(np.arange(0.0, 1.0, RUN_DT))


def test_a_report_dt_that_is_not_a_multiple_of_the_run_dt_is_an_error(tmp_path):
    circuit = write_cells_circuit(tmp_path, sections={"reports": {"soma": report(dt=0.25)}})
    with pytest.raises(ValueError, match=r"not a multiple of run\.dt"):
        NestSonataNetwork(circuit.simulation_config)


def test_the_end_time_is_cut_at_tstop(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(end_time=500.0)}, tstop=10.0)
    assert read_soma_report(path, "cells")[1][-1] == pytest.approx(9.0)


def test_cells_select_the_reported_nodes(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(cells="first", end_time=3.0)})
    assert read_soma_report(path, "cells")[0].tolist() == [0]


def test_the_top_level_node_set_gives_the_default_cells(tmp_path):
    circuit = write_cells_circuit(
        tmp_path,
        params={"I_e": 100.0},
        sections={"node_set": "first", "reports": {"soma": report(end_time=3.0)}},
    )
    network = NestSonataNetwork(circuit.simulation_config)
    network.BuildNetwork()
    network.add_report_recorders()
    network.Simulate()
    (path,) = network.write_reports()
    assert read_soma_report(path, "cells")[0].tolist() == [0]


def test_all_nodes_are_reported_without_cells_or_a_top_level_node_set(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(end_time=3.0)}, n=3)
    assert read_soma_report(path, "cells")[0].tolist() == [0, 1, 2]


def test_the_file_name_and_the_output_dir_place_the_report(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(end_time=3.0, file_name="trace")})
    assert path == tmp_path / "out" / "trace.h5"
    assert path.exists()


def test_a_disabled_report_is_not_written(tmp_path):
    _, paths = run(tmp_path, {"soma": report(end_time=3.0, enabled=False)})
    assert paths == []


@pytest.mark.parametrize(
    "extra", [{"sections": "axon"}, {"variable_name": "i_syn"}, {"type": "summation"}]
)
def test_other_reports_than_soma_v_are_not_supported(tmp_path, extra):
    circuit = write_cells_circuit(tmp_path, sections={"reports": {"soma": report(**extra)}})
    with pytest.raises(NotImplementedError, match="'compartment' reports of the 'soma'"):
        NestSonataNetwork(circuit.simulation_config)


def test_a_model_without_a_membrane_potential_is_an_error(tmp_path):
    circuit = write_cells_circuit(
        tmp_path, model="nest:parrot_neuron", sections={"reports": {"soma": report()}}
    )
    network = NestSonataNetwork(circuit.simulation_config)
    network.BuildNetwork()
    with pytest.raises(ValueError, match="has no V_m"):
        network.add_report_recorders()


def test_the_report_has_the_sonata_soma_layout(tmp_path):
    _, (path,) = run(tmp_path, {"soma": report(end_time=4.0)})
    with h5py.File(path) as handle:
        group = handle["report/cells"]
        assert group["data"].shape == (4, 2)
        assert group["data"].dtype == np.float32
        assert group["data"].attrs["units"] == "mV"
        assert group["mapping/node_ids"][:].tolist() == [0, 1]
        assert group["mapping/index_pointers"][:].tolist() == [0, 1, 2]
        assert group["mapping/element_ids"][:].tolist() == [0, 0]
        assert group["mapping/time"][:].tolist() == [0.0, 4.0, 1.0]
        assert group["mapping/time"].attrs["units"] == "ms"


def test_run_simulation_writes_spikes_and_reports(tmp_path):
    circuit = write_cells_circuit(
        tmp_path, params={"I_e": 100.0}, sections={"reports": {"soma": report(end_time=3.0)}}
    )
    results = run_simulation(circuit.simulation_config)
    assert results.spike_report_file == tmp_path / "out" / "spikes.h5"
    assert results.voltage_report_files == [tmp_path / "out" / "soma.h5"]
    assert read_soma_report(tmp_path / "out" / "soma.h5", "cells")[2].shape == (3, 2)


def test_spikes_after_tstop_are_not_in_the_spike_report(tmp_path):
    """NEST runs one minimum delay past tstop to flush the multimeter; those spikes are dropped."""
    circuit = write_cells_circuit(
        tmp_path,
        params={"I_e": 1000.0, "t_ref": 0.1},
        tstop=14.0,
        sections={"reports": {"soma": report(end_time=3.0)}},
    )
    network = NestSonataNetwork(circuit.simulation_config)
    network.BuildNetwork()
    recorders = network.add_spike_recorders()
    network.add_report_recorders()
    network.Simulate()
    network.write_reports()
    assert recorders["cells"].get("events")["times"].max() > 14.0
    path = network.write_spike_report(recorders)
    with h5py.File(path) as handle:
        assert handle["spikes/cells/timestamps"][:].max() <= 14.0


def test_frames_arithmetic():
    frames = soma_reports.Frames.of("r", start=5.0, end=20.0, dt=2.0, run_dt=0.1)
    assert (frames.first, frames.every, frames.count) == (50, 20, 8)
    assert frames.start_ms == pytest.approx(5.0)
    assert frames.end_ms == pytest.approx(21.0)
    assert frames.multimeter() == {"interval": 2.0, "offset": 1.0, "start": 4.9, "stop": 19.0}


def test_frames_from_zero_leave_the_first_to_the_initial_state():
    frames = soma_reports.Frames.of("r", start=0.0, end=3.0, dt=1.0, run_dt=0.1)
    assert frames.has_initial_frame
    assert frames.sampled == 2
    assert frames.multimeter() == {"interval": 1.0, "offset": 0.0, "start": 0.9, "stop": 2.0}


def test_frames_matrix_orders_rows_by_the_requested_nodes():
    frames = soma_reports.Frames.of("r", start=1.0, end=3.0, dt=1.0, run_dt=1.0)
    events = {
        "senders": [7, 5, 7, 5],
        "times": [2.0, 1.0, 1.0, 2.0],
        "V_m": [-1.0, -3.0, -2.0, -4.0],
    }
    matrix = soma_reports.frames_matrix(events, np.array([7, 5]), None, frames)
    assert matrix.tolist() == [[-2.0, -1.0], [-3.0, -4.0]]


def test_frames_matrix_rejects_missing_samples():
    frames = soma_reports.Frames.of("r", start=1.0, end=3.0, dt=1.0, run_dt=1.0)
    events = {"senders": [5, 7, 5], "times": [1.0, 1.0, 2.0], "V_m": [0.0, 0.0, 0.0]}
    with pytest.raises(ValueError, match="recorded 3 samples"):
        soma_reports.frames_matrix(events, np.array([5, 7]), None, frames)

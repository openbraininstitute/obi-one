import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from obi_one.scientific.library import simulation_execution as execution


@pytest.fixture
def tmp_sim_config(tmp_path: Path) -> Path:
    """Create a minimal fake simulation config JSON on disk."""
    config = {
        "run": {"tstop": 10.0, "dt": 0.1},
        "node_sets_file": "nodes.json",
        "node_set": "All",
    }
    sim_file = tmp_path / "sim.json"
    with sim_file.open("w", encoding="utf-8") as f:
        json.dump(config, f)

    nodes = {"All": {"population": "PopA", "node_id": [0]}}
    nodes_file = tmp_path / "nodes.json"
    with nodes_file.open("w", encoding="utf-8") as f:
        json.dump(nodes, f)

    return sim_file


def test_run_bluecellulab_integration(tmp_sim_config: Path) -> None:
    # Mock ParallelContext
    pc_mock = MagicMock()
    pc_mock.id.return_value = 0
    pc_mock.nhost.return_value = 1
    pc_mock.py_gather.side_effect = lambda x, _: [x]  # mimic gather
    pc_mock.barrier.return_value = None

    # Mock CircuitSimulation
    sim_mock = MagicMock()
    sim_mock.get_time_trace.return_value = np.array([0.0, 1.0, 2.0])
    sim_mock.get_voltage_trace.return_value = np.array([0.0, -65.0, -64.0])
    sim_mock.cells = {("PopA", 0): MagicMock()}
    sim_mock.cells["PopA", 0].get_recorded_spikes.return_value = [1.5, 2.5]
    sim_mock.dt = 0.1
    sim_mock.circuit_access.config = {}

    # Patch dependencies inside execution module
    with (
        patch.object(execution, "h") as h_mock,
        patch.object(execution, "CircuitSimulation", return_value=sim_mock),
        patch.object(execution, "ReportManager") as report_mgr_cls,
        patch.object(execution, "save_results_to_nwb") as save_nwb_mock,
        patch.object(execution, "plot_voltage_traces") as plot_mock,
        patch.object(execution, "_setup_file_logging", return_value=logging),
    ):
        h_mock.ParallelContext.return_value = pc_mock
        report_mgr = MagicMock()
        report_mgr_cls.return_value = report_mgr

        # Run with save_nwb=True
        execution.run_bluecellulab(tmp_sim_config, save_nwb=True)

        # Check orchestration
        sim_mock.instantiate_gids.assert_called_once()
        sim_mock.run.assert_called_once_with(10.0, 0.1, cvode=False)

        # Reports written
        report_mgr.write_all.assert_called_once()
        save_nwb_mock.assert_called_once()
        plot_mock.assert_called_once()


def test_run_bluecellulab_passes_correct_data(tmp_sim_config: Path) -> None:
    pc_mock = MagicMock()
    pc_mock.id.return_value = 0
    pc_mock.nhost.return_value = 1
    pc_mock.py_gather.side_effect = lambda x, _: [x]
    pc_mock.barrier.return_value = None

    sim_mock = MagicMock()
    sim_mock.get_time_trace.return_value = np.array([0.0, 1.0, 2.0])
    sim_mock.get_voltage_trace.return_value = np.array([-65.0, -64.5, -64.0])
    sim_mock.cells = {("PopA", 0): MagicMock()}
    sim_mock.cells["PopA", 0].get_recorded_spikes.return_value = [1.0, 2.0]
    sim_mock.dt = 0.1
    sim_mock.circuit_access.config = {}

    with (
        patch.object(execution, "h") as h_mock,
        patch.object(execution, "CircuitSimulation", return_value=sim_mock),
        patch.object(execution, "ReportManager") as report_mgr_cls,
        patch.object(execution, "_setup_file_logging", return_value=logging),
    ):
        h_mock.ParallelContext.return_value = pc_mock
        report_mgr = MagicMock()
        report_mgr_cls.return_value = report_mgr

        execution.run_bluecellulab(tmp_sim_config)

        _, kwargs = report_mgr.write_all.call_args
        traces = kwargs["cells_or_traces"]
        spikes = kwargs["spikes_by_pop"]

        assert "PopA_0" in traces
        assert "time" in traces["PopA_0"]
        assert "voltage" in traces["PopA_0"]
        assert spikes["PopA"][0] == [1.0, 2.0]


def test_distribute_cells_multi_rank(tmp_sim_config: Path) -> None:
    config_data, _, _ = execution._load_simulation_config(tmp_sim_config)

    # Two nodes across two ranks
    node_sets_file = Path(tmp_sim_config).parent / "nodes.json"
    with node_sets_file.open("w", encoding="utf-8") as f:
        json.dump({"All": {"population": "PopA", "node_id": [0, 1]}}, f)

    # Rank 0
    ids_rank0 = execution._distribute_cells(config_data, tmp_sim_config, 0, 2)
    # Rank 1
    ids_rank1 = execution._distribute_cells(config_data, tmp_sim_config, 1, 2)

    all_ids = [gid for _, gid in ids_rank0 + ids_rank1]
    assert sorted(all_ids) == [0, 1]
    assert len(ids_rank0) == len(ids_rank1) == 1


def test_gather_results_handles_missing_time_trace() -> None:
    sim_mock = MagicMock()
    sim_mock.get_time_trace.return_value = None

    pc_mock = MagicMock()
    pc_mock.py_gather.return_value = []

    results = execution._gather_results(sim_mock, [("PopA", 0)], 0, pc_mock)
    assert results == ({}, {})


def test_merge_dicts() -> None:
    dicts = [{"a": 1}, {"b": 2}, {"a": 3}]
    merged = execution._merge_dicts(dicts)
    assert merged == {"a": 3, "b": 2}


def test_merge_spikes() -> None:
    pop1 = {"popA": {0: [1.0, 2.0]}}
    pop2 = {"popA": {1: [3.0]}, "popB": {2: [4.0]}}
    merged = execution._merge_spikes([pop1, pop2])
    assert merged["popA"][0] == [1.0, 2.0]
    assert merged["popA"][1] == [3.0]
    assert merged["popB"][2] == [4.0]


def test_resolve_output_dir_manifest(tmp_path: Path) -> None:
    base_manifest = tmp_path / "bar"
    config = {
        "output": {"output_dir": "$OUTPUT_DIR/foo"},
        "manifest": {"$OUTPUT_DIR": str(base_manifest)},
    }
    out = execution._resolve_output_dir("/base/sim.json", config)
    assert str(out) == str(base_manifest / "foo")


def test_resolve_output_dir_direct(tmp_path: Path) -> None:
    direct_dir = tmp_path / "dir"
    config = {"output": {"output_dir": str(direct_dir)}}
    out = execution._resolve_output_dir("/base/sim.json", config)
    assert str(out) == str(direct_dir)


def test_resolve_output_dir_default() -> None:
    config = {}
    out = execution._resolve_output_dir("/base/sim.json", config)
    assert str(out) == "/base/output"


def test_raise_node_set_key_error() -> None:
    with pytest.raises(KeyError):
        execution._raise_node_set_key_error("foo")


def test_get_instantiate_gids_params_inputs() -> None:
    config = {"inputs": {"stim1": {"module": "noise"}}}
    params = execution.get_instantiate_gids_params(config)
    assert params["add_stimuli"] is True


def test_get_instantiate_gids_params_mechanisms() -> None:
    config = {"conditions": {"mechanisms": {"m1": {"minis_single_vesicle": True}}}}
    params = execution.get_instantiate_gids_params(config)
    assert params["add_synapses"] is True
    assert params["add_minis"] is True


def test_finalize_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    pc = MagicMock()

    fake_logger = MagicMock()
    monkeypatch.setattr(execution, "logger", fake_logger)

    execution._finalize(0, pc)

    fake_logger.info.assert_any_call("Rank %d: Cleaning up...", 0)
    fake_logger.info.assert_any_call("All ranks completed. Simulation finished.")

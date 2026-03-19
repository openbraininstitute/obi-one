import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


def _install_stub_modules(monkeypatch):
    matplotlib = ModuleType("matplotlib")
    pyplot = ModuleType("matplotlib.pyplot")
    pyplot.subplots = lambda *_args, **_kwargs: (SimpleNamespace(), [[SimpleNamespace()]])
    pyplot.savefig = lambda *_args, **_kwargs: None
    pyplot.close = lambda *_args, **_kwargs: None
    monkeypatch.setitem(sys.modules, "matplotlib", matplotlib)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", pyplot)

    numpy = ModuleType("numpy")
    numpy.array = lambda x, **_kwargs: x
    monkeypatch.setitem(sys.modules, "numpy", numpy)

    bluecellulab = ModuleType("bluecellulab")
    bluecellulab.CircuitSimulation = object
    monkeypatch.setitem(sys.modules, "bluecellulab", bluecellulab)

    bluecellulab_reports = ModuleType("bluecellulab.reports")
    bluecellulab_reports_manager = ModuleType("bluecellulab.reports.manager")
    bluecellulab_reports_manager.ReportManager = object
    monkeypatch.setitem(sys.modules, "bluecellulab.reports", bluecellulab_reports)
    monkeypatch.setitem(sys.modules, "bluecellulab.reports.manager", bluecellulab_reports_manager)

    neuron = ModuleType("neuron")
    neuron.h = SimpleNamespace(
        nrn_load_dll=lambda *_args, **_kwargs: None,
        nrnmpi_init=lambda *_args, **_kwargs: None,
        ParallelContext=lambda: SimpleNamespace(
            id=lambda: 0,
            nhost=lambda: 1,
            barrier=lambda: None,
            done=lambda: None,
        ),
        quit=lambda: None,
    )
    monkeypatch.setitem(sys.modules, "neuron", neuron)

    pynwb = ModuleType("pynwb")
    pynwb.NWBHDF5IO = object
    pynwb.NWBFile = object
    monkeypatch.setitem(sys.modules, "pynwb", pynwb)

    pynwb_icephys = ModuleType("pynwb.icephys")
    pynwb_icephys.CurrentClampSeries = object
    pynwb_icephys.IntracellularElectrode = object
    monkeypatch.setitem(sys.modules, "pynwb.icephys", pynwb_icephys)


@pytest.fixture
def test_module(monkeypatch):
    _install_stub_modules(monkeypatch)
    module = importlib.import_module("obi_one.scientific.library.simulation.entrypoint")
    return importlib.reload(module)


def test_get_instantiate_gids_params_defaults(test_module):
    params = test_module.get_instantiate_gids_params({"run": {}})
    assert params["add_stimuli"] is False
    assert params["add_synapses"] is False
    assert params["add_projections"] is False


def test_get_instantiate_gids_params_sets_flags(test_module):
    params = test_module.get_instantiate_gids_params(
        {
            "inputs": {"i1": {"module": "noise"}},
            "conditions": {"mechanisms": {"m1": {"minis_single_vesicle": True}}},
        }
    )
    assert params["add_stimuli"] is True
    assert params["add_synapses"] is True
    assert params["add_minis"] is True
    assert params["add_projections"] is True


def test_run_dispatches_backend(test_module, monkeypatch):
    called = {}

    def fake_blue(**kwargs):
        called["blue"] = kwargs

    def fake_neuro(**kwargs):
        called["neuro"] = kwargs

    monkeypatch.setattr(test_module, "run_bluecellulab", fake_blue)
    monkeypatch.setattr(test_module, "run_neurodamus", fake_neuro)

    test_module.run(
        simulation_config="cfg.json",
        simulator="BlueCelluLab",
        libnrnmech_path="lib.so",
        save_nwb=True,
    )
    assert "blue" in called
    assert called["blue"]["simulation_config"] == "cfg.json"
    assert called["blue"]["libnrnmech_path"] == "lib.so"
    assert called["blue"]["save_nwb"] is True

    test_module.run(
        simulation_config="cfg.json",
        simulator="neurodamus",
        libnrnmech_path="lib.so",
        save_nwb=False,
    )
    assert "neuro" in called


def test_run_unsupported_backend_raises(test_module):
    with pytest.raises(ValueError, match="Unsupported backend"):
        test_module.run(
            simulation_config="cfg.json",
            simulator="unknown",
            libnrnmech_path="lib.so",
            save_nwb=False,
        )


def test_main_raises_if_config_missing(test_module, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--config",
            "/does/not/exist.json",
            "--libnrnmech-path",
            "lib.so",
            "--simulation-backend",
            "bluecellulab",
        ],
    )
    with pytest.raises(RuntimeError, match="Simulation config file not found"):
        test_module.main()


def test_main_calls_run_when_config_exists(test_module, monkeypatch, tmp_path):
    config_path = tmp_path / "cfg.json"
    config_path.write_text("{}")
    called = {}

    def fake_run(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(test_module, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--config",
            str(config_path),
            "--libnrnmech-path",
            "lib.so",
            "--simulation-backend",
            "bluecellulab",
            "--save-nwb",
        ],
    )
    test_module.main()
    assert called["simulation_config"] == str(config_path)
    assert called["simulator"] == "bluecellulab"
    assert called["libnrnmech_path"] == "lib.so"
    assert called["save_nwb"] is True


def test_resolve_output_dir_defaults_to_config_parent(test_module, tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")
    out = test_module._resolve_output_dir(cfg, {"run": {}})
    assert out == tmp_path / "output"


def test_resolve_output_dir_uses_output_dir(test_module, tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")
    out = test_module._resolve_output_dir(cfg, {"output": {"output_dir": str(tmp_path / "x")}})
    assert out == tmp_path / "x"


def test_resolve_output_dir_expands_manifest_output_dir(test_module, tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")
    out = test_module._resolve_output_dir(
        cfg,
        {
            "output": {"output_dir": "$OUTPUT_DIR/results"},
            "manifest": {"$OUTPUT_DIR": str(tmp_path / "base")},
        },
    )
    assert out == tmp_path / "base" / "results"


def test_load_simulation_config(test_module, monkeypatch):
    def fake_load_json(_path):
        return {"run": {"tstop": 10.0, "dt": 0.1}}

    monkeypatch.setattr(test_module, "load_json", fake_load_json)
    data, t_stop, dt = test_module._load_simulation_config("x.json")
    assert data["run"]["tstop"] == 10.0
    assert t_stop == 10.0
    assert dt == 0.1


def test_distribute_cells_splits_ids_across_ranks(test_module, monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")

    def fake_load_json(path):
        if str(path).endswith("cfg.json"):
            return {"node_sets_file": "nodes.json", "node_set": "All"}
        return {"All": {"population": "popA", "node_id": list(range(10))}}

    monkeypatch.setattr(test_module, "load_json", fake_load_json)
    rank0 = test_module._distribute_cells(fake_load_json(cfg), cfg, 0, 3)
    rank1 = test_module._distribute_cells(fake_load_json(cfg), cfg, 1, 3)
    rank2 = test_module._distribute_cells(fake_load_json(cfg), cfg, 2, 3)
    all_gids = [gid for _pop, gid in rank0 + rank1 + rank2]
    assert sorted(all_gids) == list(range(10))


def test_distribute_cells_missing_nodeset_raises(test_module, monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")

    def fake_load_json(path):
        if str(path).endswith("cfg.json"):
            return {"node_sets_file": "nodes.json", "node_set": "Missing"}
        return {"All": {"population": "popA", "node_id": [1]}}

    monkeypatch.setattr(test_module, "load_json", fake_load_json)
    with pytest.raises(KeyError, match="Node set 'Missing' not found"):
        test_module._distribute_cells(fake_load_json(cfg), cfg, 0, 1)


def test_get_spikes_returns_empty_on_missing(test_module):
    sim = SimpleNamespace(cells={}, spike_location="soma", spike_threshold=0.0)
    assert test_module._get_spikes(sim, ("pop", 1)) == []


def test_gather_results_rank_zero_merges(test_module):
    class _Time:
        def __truediv__(self, other):
            return self

        @staticmethod
        def tolist():
            return [0.0, 0.001]

    class _Volt:
        def __init__(self, cell_id):
            self.cell_id = cell_id

        @staticmethod
        def tolist():
            return [-80.0, -79.0]

    class _PC:
        @staticmethod
        def py_gather(obj, root):
            assert root == 0
            return [obj]

    sim = SimpleNamespace(
        get_time_trace=_Time,
        get_voltage_trace=_Volt,
        cells={("popA", 1): SimpleNamespace(get_recorded_spikes=lambda **_kwargs: [0.1])},
        spike_location="soma",
        spike_threshold=0.0,
    )
    traces, spikes = test_module._gather_results(sim, [("popA", 1)], 0, _PC())
    assert "popA_1" in traces
    assert spikes["popA"][1] == [0.1]


def test_gather_results_rank_nonzero_returns_empty(test_module):
    class _Time:
        def __truediv__(self, other):
            return self

        @staticmethod
        def tolist():
            return [0.0]

    class _PC:
        @staticmethod
        def py_gather(obj, root):  # noqa :ARG004
            return [obj]

    sim = SimpleNamespace(get_time_trace=_Time, get_voltage_trace=lambda _cid: None, cells={})
    traces, spikes = test_module._gather_results(sim, [], 1, _PC())
    assert traces == {}
    assert spikes == {}

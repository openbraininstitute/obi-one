import importlib
import sys
from types import ModuleType, SimpleNamespace

import pytest


def _install_stub_modules(monkeypatch):
    matplotlib = ModuleType("matplotlib")
    pyplot = ModuleType("matplotlib.pyplot")
    pyplot.subplots = lambda *args, **kwargs: (SimpleNamespace(), [[SimpleNamespace()]])
    pyplot.savefig = lambda *args, **kwargs: None
    pyplot.close = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "matplotlib", matplotlib)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", pyplot)

    numpy = ModuleType("numpy")
    numpy.array = lambda x, **kwargs: x
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
        nrn_load_dll=lambda *args, **kwargs: None,
        nrnmpi_init=lambda *args, **kwargs: None,
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


def test_merge_dicts(test_module):
    assert test_module._merge_dicts([{"a": 1}, {"b": 2}, {"a": 3}]) == {"a": 3, "b": 2}


def test_merge_spikes(test_module):
    merged = test_module._merge_spikes(
        [
            {"pop1": {1: [0.1], 2: [0.2]}},
            {"pop1": {3: [0.3]}, "pop2": {4: [0.4]}},
        ]
    )
    assert merged["pop1"][1] == [0.1]
    assert merged["pop1"][3] == [0.3]
    assert merged["pop2"][4] == [0.4]


def test_raise_node_set_key_error(test_module):
    with pytest.raises(KeyError, match="Node set 'Foo' not found"):
        test_module._raise_node_set_key_error("Foo")


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


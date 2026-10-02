import sys
from types import SimpleNamespace

import pytest

from obi_one.scientific.library.simulation.neuron import entrypoint as test_module
from obi_one.types import SimulationBackend

from tests.obi_one.scientific.library.simulation.neuron._fakes import make_fake_resolution


def _patch_node_set_resolution(monkeypatch, per_node_set, *, node_set=None, **kwargs):
    """Patch entrypoint's libsonata.SimulationConfig and the node-set resolver."""
    simulation_config, node_sets, circuit_config = make_fake_resolution(
        per_node_set, node_set=node_set, **kwargs
    )
    monkeypatch.setattr(
        "obi_one.scientific.library.simulation.neuron."
        "entrypoint.libsonata.SimulationConfig.from_file",
        lambda _path: simulation_config,
    )
    monkeypatch.setattr(
        "obi_one.utils.circuit._merged_simulation_node_sets",
        lambda _sim_cfg: (node_sets, circuit_config),
    )


def test_get_instantiate_gids_params_defaults():
    params = test_module.get_instantiate_gids_params({"run": {}})
    assert params["add_stimuli"] is False
    assert params["add_synapses"] is False
    assert params["add_projections"] is False


def test_get_instantiate_gids_params_sets_flags():
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


def test_run_dispatches_backend(monkeypatch):
    called = {}

    def fake_blue(**kwargs):
        called["blue"] = kwargs

    def fake_neuro(**kwargs):
        called["neuro"] = kwargs

    monkeypatch.setattr(test_module, "run_bluecellulab", fake_blue)
    monkeypatch.setattr(test_module, "run_neurodamus", fake_neuro)

    test_module.run(
        simulation_config="cfg.json",
        simulator=SimulationBackend.bluecellulab,
        libnrnmech_path="lib.so",
    )
    assert "blue" in called
    assert called["blue"]["simulation_config"] == "cfg.json"
    assert called["blue"]["libnrnmech_path"] == "lib.so"

    test_module.run(
        simulation_config="cfg.json",
        simulator=SimulationBackend.neurodamus,
        libnrnmech_path="lib.so",
    )
    assert "neuro" in called


def test_run_unsupported_backend_raises():
    with pytest.raises(ValueError, match="Unsupported backend"):
        test_module.run(
            simulation_config="cfg.json",
            simulator="unknown",
            libnrnmech_path="lib.so",
        )


def test_main_raises_if_config_missing(monkeypatch):
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


def test_main_calls_run_when_config_exists(monkeypatch, tmp_path):
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


def test_distribute_cells_splits_ids_across_ranks(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")

    _patch_node_set_resolution(monkeypatch, {"All": {"popA": list(range(10))}}, node_set="All")

    config_data = {"node_set": "All"}
    n0, rank0 = test_module._distribute_cells(config_data, cfg, 0, 3)
    n1, rank1 = test_module._distribute_cells(config_data, cfg, 1, 3)
    n2, rank2 = test_module._distribute_cells(config_data, cfg, 2, 3)
    all_gids = [gid for _pop, gid in rank0 + rank1 + rank2]
    assert n0 == n1 == n2 == 10
    assert sorted(all_gids) == list(range(10))
    assert all(pop == "popA" for pop, _gid in rank0 + rank1 + rank2)


def test_distribute_cells_symbolic_multipopulation(monkeypatch, tmp_path):
    """A symbolic node set spanning multiple populations is resolved and split."""
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")

    _patch_node_set_resolution(
        monkeypatch,
        {"Excitatory": {"popA": [1, 2, 3], "popB": [10, 20]}},
        node_set="Excitatory",
    )

    config_data = {"node_set": "Excitatory"}
    n0, rank0 = test_module._distribute_cells(config_data, cfg, 0, 2)
    n1, rank1 = test_module._distribute_cells(config_data, cfg, 1, 2)
    assert n0 == n1 == 5
    assert sorted(rank0 + rank1) == [
        ("popA", 1),
        ("popA", 2),
        ("popA", 3),
        ("popB", 10),
        ("popB", 20),
    ]


def test_distribute_cells_simulation_only_node_set(monkeypatch, tmp_path):
    """A node set defined only in the simulation node_sets_file (not the circuit)."""
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")

    # Resolves only in popA; popB exists in the circuit but the node set does not apply.
    _patch_node_set_resolution(
        monkeypatch,
        {"MySimOnlySet": {"popA": [4, 5]}},
        node_set="MySimOnlySet",
        extra_populations=["popB"],
    )

    n, cells = test_module._distribute_cells({"node_set": "MySimOnlySet"}, cfg, 0, 1)
    assert n == 2
    assert sorted(cells) == [("popA", 4), ("popA", 5)]


def test_distribute_cells_missing_nodeset_raises(monkeypatch, tmp_path):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")

    _patch_node_set_resolution(monkeypatch, {"All": {"popA": [1]}}, node_set="Missing")

    with pytest.raises(KeyError, match="Node set 'Missing' not found"):
        test_module._distribute_cells({"node_set": "Missing"}, cfg, 0, 1)


def test_gather_results_collects_and_gathers(monkeypatch):
    calls = {}

    def fake_collect_local_payload(cells, cell_ids, recording_index):
        calls["payload_in"] = (cells, cell_ids, recording_index)
        return {"payload": 1}

    def fake_collect_local_spikes(sim, cell_ids):
        calls["spikes_in"] = (sim, cell_ids)
        return {"spikes": 2}

    def fake_gather_payload_to_rank0(parallel_context, local_payload, local_spikes):
        calls["gather_in"] = (parallel_context, local_payload, local_spikes)
        return [{"merged": 3}], {"popA": {1: [0.1]}}

    monkeypatch.setattr(test_module, "collect_local_payload", fake_collect_local_payload)
    monkeypatch.setattr(test_module, "collect_local_spikes", fake_collect_local_spikes)
    monkeypatch.setattr(test_module, "gather_payload_to_rank0", fake_gather_payload_to_rank0)

    class _PC:
        @staticmethod
        def py_gather(obj, root):
            assert root == 0
            return [obj]

    process = SimpleNamespace(parallel_context=_PC())
    sim = SimpleNamespace(cells={"k": "v"})

    gathered_sites, all_payload, all_spikes = test_module._gather_results(
        sim=sim,
        cell_ids_for_this_rank=[("popA", 1)],
        process=process,
        recording_index={"r": 1},
        local_sites_index={"site": 1},
    )

    assert gathered_sites == [{"site": 1}]
    assert all_payload == [{"merged": 3}]
    assert all_spikes == {"popA": {1: [0.1]}}
    assert calls["payload_in"] == (sim.cells, [("popA", 1)], {"r": 1})
    assert calls["spikes_in"] == (sim, [("popA", 1)])
    assert calls["gather_in"] == (process.parallel_context, {"payload": 1}, {"spikes": 2})

"""Circuit builders shared by the NEST simulation tests."""

import shutil
from pathlib import Path
from typing import NamedTuple

import h5py
import libsonata
import numpy as np

from obi_one.utils.io import write_json

MODELS = Path(__file__).parent / "data" / "models"


class NestCircuitPaths(NamedTuple):
    circuit_config: Path
    simulation_config: Path


def _write_enumeration(group: h5py.Group, name: str, values: list[str]) -> None:
    library = sorted(set(values))
    group.create_dataset(name, data=np.array([library.index(v) for v in values], dtype=np.uint32))
    group.create_dataset(f"@library/{name}", data=np.array(library, dtype=h5py.string_dtype()))


def _write_edges(
    path: Path,
    name: str,
    populations: tuple[str, str],
    connections: tuple[list[int], list[int]],
    template: str,
    datasets: dict[str, list[float]] | None = None,
    dynamics: dict[str, list[float]] | None = None,
) -> None:
    sources, targets = connections
    with h5py.File(path, "w") as handle:
        group = handle.create_group(f"edges/{name}")
        group.create_dataset("source_node_id", data=np.array(sources, dtype=np.uint64))
        group.create_dataset("target_node_id", data=np.array(targets, dtype=np.uint64))
        group["source_node_id"].attrs["node_population"] = populations[0]
        group["target_node_id"].attrs["node_population"] = populations[1]
        group.create_dataset("edge_type_id", data=np.full(len(sources), -1))
        group.create_dataset("edge_group_id", data=np.zeros(len(sources), dtype=np.uint32))
        group.create_dataset("edge_group_index", data=np.arange(len(sources), dtype=np.uint64))
        zero = group.create_group("0")
        _write_enumeration(zero, "model_template", [template] * len(sources))
        for key, values in (datasets or {}).items():
            zero.create_dataset(key, data=np.array(values))
        for key, values in (dynamics or {}).items():
            zero.create_dataset(f"dynamics_params/{key}", data=np.array(values))


def write_spikes(path: Path, population: str, node_ids: list[int], times: list[float]) -> None:
    """Write a SONATA spike file with the spikes of one *population*, sorted by time."""
    order = np.argsort(times, kind="stable")
    with h5py.File(path, "w") as handle:
        group = handle.create_group(f"spikes/{population}")
        group.attrs.create(
            "sorting", data=2, dtype=h5py.enum_dtype({"none": 0, "by_id": 1, "by_time": 2})
        )
        group.create_dataset("node_ids", data=np.array(node_ids, dtype=np.uint64)[order])
        timestamps = group.create_dataset(
            "timestamps", data=np.array(times, dtype=np.float64)[order]
        )
        timestamps.attrs["units"] = "ms"


def write_nest_circuit(root: Path, input_weight: float = 50.0) -> NestCircuitPaths:
    """Write a small SONATA-extension NEST circuit.

    - population ``exc``: 4 ``nest_point`` nodes from two templates with different parameters;
    - population ``input``: 2 ``virtual`` nodes, replayed to ``exc`` by a ``synapse_replay`` input;
    - edges ``input__exc``: ``static_synapse`` with template-level ``delay``/``weight``;
    - edges ``exc__exc``: ``tsodyks2_synapse`` with per-edge ``syn_weight``/``delay`` and
      ``U``/``u``/``tau_rec``/``tau_fac`` dynamics parameters.
    """
    network = root / "network"
    network.mkdir(parents=True)
    exc_templates = root / "model_templates" / "exc"
    exc_templates.mkdir(parents=True)
    write_json(
        {"model": "nest:iaf_psc_alpha", "params": {"V_th": -50.0, "C_m": 200.0}},
        exc_templates / "iaf_psc_alpha_type1.json",
    )
    write_json(
        {"model": "nest:iaf_psc_alpha", "params": {"V_th": -45.0, "C_m": 250.0}},
        exc_templates / "iaf_psc_alpha_type2.json",
    )
    stp_templates = root / "model_templates" / "exc__exc"
    stp_templates.mkdir(parents=True)
    write_json(
        {
            "model": "nest:tsodyks2_synapse",
            "params": {"U": 0.5, "u": 0.5, "tau_rec": 500.0, "tau_fac": 20.0},
            "dynamics_params": {"U": "1", "u": "1", "tau_rec": "ms", "tau_fac": "ms"},
        },
        stp_templates / "tsodyks2_synapse.json",
    )
    static_templates = root / "model_templates" / "input__exc"
    static_templates.mkdir(parents=True)
    write_json(
        {"model": "nest:static_synapse", "params": {"delay": 2.0, "weight": input_weight}},
        static_templates / "static_synapse.json",
    )

    with h5py.File(network / "exc_nodes.h5", "w") as handle:
        group = handle.create_group("nodes/exc")
        group.create_dataset("node_type_id", data=np.full(4, -1))
        zero = group.create_group("0")
        _write_enumeration(zero, "model_type", ["nest_point"] * 4)
        _write_enumeration(
            zero, "model_template", ["iaf_psc_alpha_type1"] * 2 + ["iaf_psc_alpha_type2"] * 2
        )
    with h5py.File(network / "input_nodes.h5", "w") as handle:
        group = handle.create_group("nodes/input")
        group.create_dataset("node_type_id", data=np.full(2, -1))
        _write_enumeration(group.create_group("0"), "model_type", ["virtual"] * 2)

    _write_edges(
        network / "input_exc_edges.h5",
        "input__exc",
        ("input", "exc"),
        ([0, 1], [0, 2]),
        "static_synapse",
    )
    _write_edges(
        network / "exc_exc_edges.h5",
        "exc__exc",
        ("exc", "exc"),
        ([0, 1, 2], [1, 2, 3]),
        "tsodyks2_synapse",
        datasets={"syn_weight": [1.0, 2.0, 3.0], "delay": [1.5, 2.5, 3.5]},
        dynamics={
            "U": [0.1, 0.2, 0.3],
            "u": [0.1, 0.2, 0.3],
            "tau_rec": [100.0, 200.0, 300.0],
            "tau_fac": [10.0, 20.0, 30.0],
        },
    )

    inputs = root / "inputs"
    inputs.mkdir()
    write_spikes(inputs / "input_spikes.h5", "input", [0, 1, 0, 1], [5.0, 7.0, 15.0, 30.0])

    write_json(
        {"exc": {"population": "exc"}, "input": {"population": "input"}}, root / "node_sets.json"
    )
    circuit_config = root / "circuit_config.json"
    write_json(
        {
            "version": 2,
            "target_simulator": "NEST",
            "manifest": {"$BASE_DIR": "."},
            "node_sets_file": "$BASE_DIR/node_sets.json",
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "$BASE_DIR/network/exc_nodes.h5",
                        "populations": {
                            "exc": {
                                "type": "nest_point",
                                "point_neuron_models_dir": "$BASE_DIR/model_templates/exc",
                            }
                        },
                    },
                    {
                        "nodes_file": "$BASE_DIR/network/input_nodes.h5",
                        "populations": {"input": {"type": "virtual"}},
                    },
                ],
                "edges": [
                    {
                        "edges_file": "$BASE_DIR/network/input_exc_edges.h5",
                        "populations": {
                            "input__exc": {
                                "type": "nest_chemical",
                                "point_neuron_models_dir": "$BASE_DIR/model_templates/input__exc",
                            }
                        },
                    },
                    {
                        "edges_file": "$BASE_DIR/network/exc_exc_edges.h5",
                        "populations": {
                            "exc__exc": {
                                "type": "nest_chemical",
                                "point_neuron_models_dir": "$BASE_DIR/model_templates/exc__exc",
                            }
                        },
                    },
                ],
            },
        },
        circuit_config,
    )
    simulation_config = root / "simulation_config.json"
    write_json(
        {
            "version": 2,
            "manifest": {"$BASE_DIR": "."},
            "network": "$BASE_DIR/circuit_config.json",
            "target_simulator": "NEST",
            "run": {"dt": 0.1, "tstop": 20.0, "random_seed": 0},
            "inputs": {
                "input_spikes": {
                    "input_type": "spikes",
                    "module": "synapse_replay",
                    "spike_file": "$BASE_DIR/inputs/input_spikes.h5",
                    "node_set": "exc",
                    "delay": 0.0,
                    "duration": 20.0,
                }
            },
        },
        simulation_config,
    )
    return NestCircuitPaths(circuit_config, simulation_config)


def write_nestml_circuit(root: Path, model_name: str, tstop: float = 10.0) -> Path:
    """Write a 1-neuron SONATA-extension circuit whose template uses ``nestml:<model_name>``.

    Returns the simulation config path.
    """
    pop = "toy"
    template_dir = root / "model_templates" / pop
    template_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(MODELS / f"{model_name}.nestml", template_dir / f"{model_name}.nestml")
    write_json({"model": f"nestml:{model_name}"}, template_dir / f"{model_name}.json")

    nodes_file = root / pop / "nodes.h5"
    nodes_file.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(nodes_file, "w") as handle:
        grp = handle.create_group(f"nodes/{pop}")
        grp.create_dataset("node_type_id", data=[-1])
        zero = grp.create_group("0")
        _write_enumeration(zero, "model_type", ["nest_point"])
        zero.create_dataset("model_template", data=np.array([0], dtype=np.uint32))
        zero.create_dataset(
            "@library/model_template", data=np.array([model_name], dtype=h5py.string_dtype())
        )

    write_json(
        {
            "version": 2,
            "target_simulator": "NEST",
            "manifest": {"$BASE_DIR": "."},
            "node_sets_file": "$BASE_DIR/node_sets.json",
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "$BASE_DIR/toy/nodes.h5",
                        "populations": {
                            pop: {
                                "type": "nest_point",
                                "point_neuron_models_dir": f"$BASE_DIR/model_templates/{pop}",
                            }
                        },
                    }
                ],
                "edges": [],
            },
        },
        root / "circuit_config.json",
    )
    write_json({pop: {"population": pop}}, root / "node_sets.json")
    sim = root / "simulation_config.json"
    write_json(
        {
            "manifest": {"$BASE_DIR": "."},
            "network": "$BASE_DIR/circuit_config.json",
            "target_simulator": "NEST",
            "run": {"dt": 0.1, "tstop": tstop, "random_seed": 0},
        },
        sim,
    )
    return sim


def write_cells_circuit(
    root: Path,
    *,
    model: str = "nest:iaf_psc_alpha",
    params: dict | None = None,
    n: int = 2,
    tstop: float = 50.0,
    sections: dict | None = None,
) -> NestCircuitPaths:
    """Write a circuit of *n* ``cells`` nodes without edges, and a simulation config for it.

    *sections* are added to the simulation config (``inputs``, ``reports``, ...). The node sets
    are ``cells``, and ``first`` for node 0.
    """
    templates = root / "model_templates" / "cells"
    templates.mkdir(parents=True)
    write_json({"model": model, "params": params or {}}, templates / "cell.json")
    (root / "network").mkdir()
    with h5py.File(root / "network" / "cells_nodes.h5", "w") as handle:
        group = handle.create_group("nodes/cells")
        group.create_dataset("node_type_id", data=np.full(n, -1))
        zero = group.create_group("0")
        _write_enumeration(zero, "model_type", ["nest_point"] * n)
        _write_enumeration(zero, "model_template", ["cell"] * n)
    circuit_config = root / "circuit_config.json"
    write_json(
        {
            "version": 2,
            "target_simulator": "NEST",
            "manifest": {"$BASE_DIR": "."},
            "node_sets_file": "$BASE_DIR/node_sets.json",
            "networks": {
                "nodes": [
                    {
                        "nodes_file": "$BASE_DIR/network/cells_nodes.h5",
                        "populations": {
                            "cells": {
                                "type": "nest_point",
                                "point_neuron_models_dir": "$BASE_DIR/model_templates/cells",
                            }
                        },
                    }
                ],
                "edges": [],
            },
        },
        circuit_config,
    )
    write_json(
        {"cells": {"population": "cells"}, "first": {"population": "cells", "node_id": [0]}},
        root / "node_sets.json",
    )
    simulation_config = root / "simulation_config.json"
    write_json(
        {
            "version": 2,
            "manifest": {"$BASE_DIR": "."},
            "network": "$BASE_DIR/circuit_config.json",
            "target_simulator": "NEST",
            "run": {"dt": 0.1, "tstop": tstop, "random_seed": 0},
            "output": {"output_dir": "$BASE_DIR/out", "spikes_file": "spikes.h5"},
            **(sections or {}),
        },
        simulation_config,
    )
    return NestCircuitPaths(circuit_config, simulation_config)


def read_soma_report(path: Path, population: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The node ids, frame times and ``(frames, nodes)`` data of a report, read with libsonata."""
    frame = libsonata.SomaReportReader(str(path))[population].get()
    return np.asarray(frame.ids), np.asarray(frame.times), np.asarray(frame.data)

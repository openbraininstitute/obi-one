"""A NEST export laid out as sonata-simplify writes it, for tests."""

import json
from pathlib import Path

import h5py
import numpy as np

N_NEURONS = 3
N_VPM = 2


def _write_nodes(path: Path, population: str, size: int, *, with_dynamics: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        group = f.create_group(f"nodes/{population}")
        group.create_dataset("node_type_id", data=np.full(size, -1, dtype=np.int64))
        if with_dynamics:
            group.create_dataset("0/dynamics_params/C_m", data=np.full(size, 200.0))


def _write_edges(path: Path, population: str, source: str, target: str, pairs: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sources, targets = np.array(pairs, dtype=np.uint64).T
    with h5py.File(path, "w") as f:
        group = f.create_group(f"edges/{population}")
        group.create_dataset("source_node_id", data=sources).attrs["node_population"] = source
        group.create_dataset("target_node_id", data=targets).attrs["node_population"] = target
        group.create_dataset("edge_type_id", data=np.full(len(pairs), -1, dtype=np.int64))
        group.create_dataset("edge_group_id", data=np.zeros(len(pairs), dtype=np.int32))
        group.create_dataset("edge_group_index", data=np.arange(len(pairs), dtype=np.int64))
        group.create_dataset("0/syn_weight", data=np.ones(len(pairs)))
        group.create_dataset("0/delay", data=np.full(len(pairs), 1.0))


def _write_types(path: Path, header: str, row: str) -> None:
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")


def write_nest_export(export_dir: Path) -> Path:
    """A NEST export laid out as sonata-simplify writes it: one point and one virtual population."""
    _write_nodes(export_dir / "neurons/nodes.h5", "neurons", N_NEURONS, with_dynamics=True)
    _write_types(
        export_dir / "neurons/nodes_types.csv",
        "node_type_id model_type model_template dynamics_params",
        "-1 point_neuron nest:aeif_cond_alpha neurons/dynamics_params/params_-1.json",
    )
    _write_nodes(export_dir / "VPM/nodes.h5", "VPM", N_VPM, with_dynamics=False)
    _write_types(
        export_dir / "VPM/nodes_types.csv",
        "node_type_id model_type model_template dynamics_params",
        "-1 virtual nest:spike_generator VPM/dynamics_params/params_-1.json",
    )
    edge_header = "edge_type_id model_template dynamics_params"
    for population, source, pairs in (
        ("neurons__neurons__chemical", "neurons", [(0, 1), (1, 2), (2, 0)]),
        ("VPM__neurons__chemical", "VPM", [(0, 0), (1, 2)]),
    ):
        _write_edges(export_dir / population / "edges.h5", population, source, "neurons", pairs)
        _write_types(
            export_dir / population / "edges_types.csv",
            edge_header,
            f"-1 static_synapse {population}/synapse_dynamics_params/synapse_params_-1.json",
        )
    config = {
        "target_simulator": "NEST",
        "manifest": {"$BASE_DIR": "."},
        "components": {"point_neuron_models_dir": "$BASE_DIR", "synaptic_models_dir": "$BASE_DIR"},
        "run": {"dt": 0.1},
        "networks": {
            "nodes": [
                {
                    "nodes_file": f"$BASE_DIR/{name}/nodes.h5",
                    "node_types_file": f"$BASE_DIR/{name}/nodes_types.csv",
                }
                for name in ("neurons", "VPM")
            ],
            "edges": [
                {
                    "edges_file": f"$BASE_DIR/{name}/edges.h5",
                    "edge_types_file": f"$BASE_DIR/{name}/edges_types.csv",
                }
                for name in ("neurons__neurons__chemical", "VPM__neurons__chemical")
            ],
        },
    }
    config_path = export_dir / "circuit_config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path

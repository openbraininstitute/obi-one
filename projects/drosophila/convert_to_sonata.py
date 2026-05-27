#!/usr/bin/env python3
"""Convert FlyWire Drosophila connectome (v783) to SONATA circuit format.

Reads the FlyWire completeness CSV and connectivity parquet, and produces
a SONATA-compliant circuit directory suitable for NEST or NEST GPU simulation.

The SONATA circuit contains:
  - Internal nodes: ~138K LIF neurons (iaf_psc_alpha)
  - Internal edges: ~15M synaptic connections with signed weights
  - External nodes: Virtual Poisson input sources for stimulated neurons
  - External edges: Connections from Poisson sources to stimulated neurons
  - Pre-generated Poisson spike trains in SONATA spikes format

Key design choice: C_m is set equal to tau_m (20.0) in the SONATA neuron params so that I/C_m =     
  g/tau_m, making the original benchmark weights transfer directly without any unit conversion. 

Weight convention:
  The original fly-brain model uses a custom LIF where synaptic input enters
  the voltage equation as g/tau_m (unitless). To reproduce identical dynamics
  with NEST's iaf_psc_alpha, we set C_m = tau_m so that I/C_m = I/tau_m,
  making the weight values transfer directly without conversion.

Usage:
    python convert_to_sonata.py
    python convert_to_sonata.py --data-dir ../../fly-brain/data --output-dir ./sonata_circuit
    python convert_to_sonata.py --experiment p9 --duration 5000 --seed 123
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

import h5py
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Experiment definitions (from fly-brain/code/benchmark.py)
# ---------------------------------------------------------------------------

EXPERIMENTS = {
    "sugar": {
        "name": "Sugar GRNs (200 Hz)",
        "neu_exc": [
            720575940624963786, 720575940630233916, 720575940637568838,
            720575940638202345, 720575940617000768, 720575940630797113,
            720575940632889389, 720575940621754367, 720575940621502051,
            720575940640649691, 720575940639332736, 720575940616885538,
            720575940639198653, 720575940639259967, 720575940617937543,
            720575940632425919, 720575940633143833, 720575940612670570,
            720575940628853239, 720575940629176663, 720575940611875570,
        ],
        "stim_rate": 200.0,
    },
    "p9": {
        "name": "P9s forward walking (100 Hz)",
        "neu_exc": [720575940627652358, 720575940635872101],
        "stim_rate": 100.0,
    },
}

# Model parameters (matching fly-brain/code/run_nestgpu.py)
W_SYN = 0.275       # mV  per-synapse weight scaling
F_POI = 250          # Poisson weight multiplier
V_REST = -52.0       # mV  resting / reset potential
V_TH = -45.0         # mV  spike threshold
TAU_M = 20.0         # ms  membrane time constant
TAU_SYN = 5.0        # ms  synaptic time constant (alpha)
T_REF = 2.2          # ms  refractory period
T_DLY = 1.8          # ms  synaptic delay
T_DLY_POI = 0.1      # ms  Poisson input delay

# SONATA HDF5 header
SONATA_MAGIC = np.uint32(0x0A7A)
SONATA_VERSION = np.array([0, 1], dtype=np.uint32)


# ---------------------------------------------------------------------------
# HDF5 writers
# ---------------------------------------------------------------------------

def _set_sonata_attrs(h5file: h5py.File) -> None:
    h5file.attrs["magic"] = SONATA_MAGIC
    h5file.attrs["version"] = SONATA_VERSION


def write_internal_nodes(
    path: Path,
    n_neurons: int,
    flywire_ids: np.ndarray,
) -> None:
    """Write internal (simulated) neuron nodes to SONATA HDF5."""
    with h5py.File(path, "w") as f:
        _set_sonata_attrs(f)
        pop = f.create_group("nodes/internal")
        pop.create_dataset("node_id", data=np.arange(n_neurons, dtype=np.uint64))
        pop.create_dataset("node_type_id", data=np.zeros(n_neurons, dtype=np.uint32))
        pop.create_dataset("node_group_id", data=np.zeros(n_neurons, dtype=np.uint32))
        pop.create_dataset("node_group_index", data=np.arange(n_neurons, dtype=np.uint64))
        grp = pop.create_group("0")
        grp.create_dataset("flywire_id", data=flywire_ids.astype(np.int64))


def write_external_nodes(path: Path, n_external: int) -> None:
    """Write external (virtual) Poisson input nodes to SONATA HDF5."""
    with h5py.File(path, "w") as f:
        _set_sonata_attrs(f)
        pop = f.create_group("nodes/external")
        pop.create_dataset("node_id", data=np.arange(n_external, dtype=np.uint64))
        pop.create_dataset("node_type_id", data=np.full(n_external, 100, dtype=np.uint32))
        pop.create_dataset("node_group_id", data=np.zeros(n_external, dtype=np.uint32))
        pop.create_dataset("node_group_index", data=np.arange(n_external, dtype=np.uint64))
        pop.create_group("0")


def write_internal_edges(
    path: Path,
    pre_idx: np.ndarray,
    post_idx: np.ndarray,
    weights: np.ndarray,
) -> None:
    """Write internal-to-internal synaptic edges to SONATA HDF5."""
    n_edges = len(pre_idx)
    with h5py.File(path, "w") as f:
        _set_sonata_attrs(f)
        pop = f.create_group("edges/internal_to_internal")

        ds_src = pop.create_dataset("source_node_id", data=pre_idx.astype(np.uint64))
        ds_src.attrs["node_population"] = "internal"
        ds_tgt = pop.create_dataset("target_node_id", data=post_idx.astype(np.uint64))
        ds_tgt.attrs["node_population"] = "internal"

        pop.create_dataset("edge_type_id", data=np.zeros(n_edges, dtype=np.uint32))
        pop.create_dataset("edge_group_id", data=np.zeros(n_edges, dtype=np.uint32))
        pop.create_dataset("edge_group_index", data=np.arange(n_edges, dtype=np.uint64))

        grp = pop.create_group("0")
        grp.create_dataset("syn_weight", data=weights.astype(np.float64))
        grp.create_dataset("delay", data=np.full(n_edges, T_DLY, dtype=np.float64))


def write_external_edges(
    path: Path,
    stim_indices: list[int],
) -> None:
    """Write external-to-internal (Poisson input) edges to SONATA HDF5."""
    n_ext = len(stim_indices)
    weight = W_SYN * F_POI  # 68.75

    with h5py.File(path, "w") as f:
        _set_sonata_attrs(f)
        pop = f.create_group("edges/external_to_internal")

        ds_src = pop.create_dataset(
            "source_node_id", data=np.arange(n_ext, dtype=np.uint64),
        )
        ds_src.attrs["node_population"] = "external"
        ds_tgt = pop.create_dataset(
            "target_node_id", data=np.array(stim_indices, dtype=np.uint64),
        )
        ds_tgt.attrs["node_population"] = "internal"

        pop.create_dataset("edge_type_id", data=np.zeros(n_ext, dtype=np.uint32))
        pop.create_dataset("edge_group_id", data=np.zeros(n_ext, dtype=np.uint32))
        pop.create_dataset("edge_group_index", data=np.arange(n_ext, dtype=np.uint64))

        grp = pop.create_group("0")
        grp.create_dataset("syn_weight", data=np.full(n_ext, weight, dtype=np.float64))
        grp.create_dataset("delay", data=np.full(n_ext, T_DLY_POI, dtype=np.float64))


# ---------------------------------------------------------------------------
# CSV / JSON writers
# ---------------------------------------------------------------------------

def write_node_types_csv(path: Path, node_type_id: int, model_template: str,
                         dynamics_params: str) -> None:
    path.write_text(
        "node_type_id,model_type,model_template,dynamics_params\n"
        f"{node_type_id},point_process,{model_template},{dynamics_params}\n"
    )


def write_virtual_node_types_csv(path: Path, node_type_id: int = 100) -> None:
    path.write_text(
        "node_type_id,model_type\n"
        f"{node_type_id},virtual\n"
    )


def write_edge_types_csv(path: Path, edge_type_id: int = 0) -> None:
    path.write_text(
        "edge_type_id,model_template\n"
        f"{edge_type_id},static_synapse\n"
    )


def write_dynamics_params(path: Path) -> None:
    """Write iaf_psc_alpha neuron parameters.

    C_m is set equal to tau_m so that I/C_m = I/tau_m, making SONATA weights
    directly equivalent to the original model's unitless weights. This gives
    R_m = tau_m/C_m = 1 GOhm (unrealistic but dynamically correct).
    """
    params = {
        "E_L": V_REST,
        "V_th": V_TH,
        "V_reset": V_REST,
        "V_min": -1e10,
        "C_m": TAU_M,          # <-- key trick: C_m = tau_m for unit matching
        "tau_m": TAU_M,
        "tau_syn_ex": TAU_SYN,
        "tau_syn_in": TAU_SYN,
        "t_ref": T_REF,
        "I_e": 0.0,
    }
    path.write_text(json.dumps(params, indent=2) + "\n")


def write_circuit_config(path: Path) -> None:
    config = {
        "manifest": {
            "$BASE_DIR": "${configdir}",
            "$NETWORK_DIR": "$BASE_DIR/network",
            "$COMPONENTS_DIR": "$BASE_DIR/components",
        },
        "target_simulator": "NEST",
        "components": {
            "point_neuron_models_dir": "$COMPONENTS_DIR/cell_models",
        },
        "networks": {
            "nodes": [
                {
                    "nodes_file": "$NETWORK_DIR/internal_nodes.h5",
                    "node_types_file": "$NETWORK_DIR/internal_node_types.csv",
                },
                {
                    "nodes_file": "$NETWORK_DIR/external_nodes.h5",
                    "node_types_file": "$NETWORK_DIR/external_node_types.csv",
                },
            ],
            "edges": [
                {
                    "edges_file": "$NETWORK_DIR/internal_internal_edges.h5",
                    "edge_types_file": "$NETWORK_DIR/internal_internal_edge_types.csv",
                },
                {
                    "edges_file": "$NETWORK_DIR/external_internal_edges.h5",
                    "edge_types_file": "$NETWORK_DIR/external_internal_edge_types.csv",
                },
            ],
        },
    }
    path.write_text(json.dumps(config, indent=2) + "\n")


def write_simulation_config(
    path: Path,
    duration_ms: float,
    experiment: dict,
) -> None:
    config = {
        "manifest": {
            "$BASE_DIR": "${configdir}",
            "$OUTPUT_DIR": "$BASE_DIR/output",
            "$INPUT_DIR": "$BASE_DIR/inputs",
        },
        "target_simulator": "NEST",
        "run": {
            "tstop": duration_ms,
            "dt": 0.1,
            "random_seed": 42,
        },
        "network": "$BASE_DIR/circuit_config.json",
        "node_sets_file": "$BASE_DIR/node_sets.json",
        "conditions": {
            "v_init": V_REST,
        },
        "metadata": {
            "experiment": experiment["name"],
            "stim_rate_hz": experiment["stim_rate"],
        },
        "inputs": {
            "poisson_input": {
                "input_type": "spikes",
                "module": "h5",
                "input_file": "$INPUT_DIR/poisson_spikes.h5",
                "node_set": "external",
            },
        },
        "output": {
            "output_dir": "$OUTPUT_DIR",
            "spikes_file": "spikes.h5",
            "spikes_sort_order": "time",
            "log_file": "log.txt",
        },
        "reports": {
            "membrane_potential": {
                "cells": "stimulated_neurons",
                "variable_name": "V_m",
                "module": "membrane_report",
                "sections": "soma",
                "dt": 0.1,
                "start_time": 0.0,
                "end_time": duration_ms,
            },
        },
    }
    path.write_text(json.dumps(config, indent=2) + "\n")


def write_node_sets(
    path: Path,
    stim_indices: list[int],
    sugar_indices: list[int],
    p9_indices: list[int],
) -> None:
    node_sets = {
        "internal": {"population": "internal"},
        "external": {"population": "external"},
        "stimulated_neurons": {
            "population": "internal",
            "node_id": stim_indices,
        },
        "sugar_grns": {
            "population": "internal",
            "node_id": sugar_indices,
        },
        "p9_neurons": {
            "population": "internal",
            "node_id": p9_indices,
        },
    }
    path.write_text(json.dumps(node_sets, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Poisson spike generation
# ---------------------------------------------------------------------------

def generate_poisson_spikes(
    path: Path,
    n_nodes: int,
    rate_hz: float,
    duration_ms: float,
    seed: int = 42,
) -> int:
    """Generate Poisson spike trains and write to SONATA spikes HDF5.

    Returns the total number of spikes generated.
    """
    rng = np.random.default_rng(seed)
    duration_s = duration_ms / 1000.0

    all_times: list[np.ndarray] = []
    all_ids: list[np.ndarray] = []

    for nid in range(n_nodes):
        n_spikes = rng.poisson(rate_hz * duration_s)
        if n_spikes > 0:
            times = np.sort(rng.uniform(0.0, duration_ms, n_spikes))
            all_times.append(times)
            all_ids.append(np.full(n_spikes, nid, dtype=np.uint64))

    if all_times:
        timestamps = np.concatenate(all_times)
        node_ids = np.concatenate(all_ids)
        sort_idx = np.argsort(timestamps)
        timestamps = timestamps[sort_idx]
        node_ids = node_ids[sort_idx]
    else:
        timestamps = np.array([], dtype=np.float64)
        node_ids = np.array([], dtype=np.uint64)

    with h5py.File(path, "w") as f:
        pop = f.create_group("spikes/external")
        ds_ts = pop.create_dataset("timestamps", data=timestamps)
        ds_ts.attrs["units"] = "ms"
        pop.create_dataset("node_ids", data=node_ids)
        pop.attrs["sorting"] = "by_time"

    return len(timestamps)


# ---------------------------------------------------------------------------
# Main conversion
# ---------------------------------------------------------------------------

def convert(
    data_dir: Path,
    output_dir: Path,
    experiment_name: str = "sugar",
    duration_ms: float = 1000.0,
    seed: int = 42,
) -> None:
    experiment = EXPERIMENTS[experiment_name]
    stim_rate = experiment["stim_rate"]
    stim_ids_flywire = experiment["neu_exc"]

    print(f"Experiment:  {experiment['name']}")
    print(f"Duration:    {duration_ms} ms")
    print(f"Stim neurons: {len(stim_ids_flywire)} at {stim_rate} Hz")
    print()

    # -- Read source data --
    t0 = perf_counter()
    print("Reading completeness CSV...")
    df_comp = pd.read_csv(data_dir / "2025_Completeness_783.csv", index_col=0)
    n_neurons = len(df_comp)
    flywire_ids = df_comp.index.values
    flyid2idx = {fid: idx for idx, fid in enumerate(flywire_ids)}
    print(f"  {n_neurons:,} neurons loaded")

    # Map experiment FlyWire IDs to SONATA node indices
    sugar_indices = [flyid2idx[fid] for fid in EXPERIMENTS["sugar"]["neu_exc"]]
    p9_indices = [flyid2idx[fid] for fid in EXPERIMENTS["p9"]["neu_exc"]]
    stim_indices = [flyid2idx[fid] for fid in stim_ids_flywire]

    print("Reading connectivity parquet...")
    df_con = pd.read_parquet(data_dir / "2025_Connectivity_783.parquet")
    n_edges = len(df_con)
    print(f"  {n_edges:,} edges loaded")

    # Validate index ranges
    assert df_con["Presynaptic_Index"].max() < n_neurons, "Pre-index out of range"
    assert df_con["Postsynaptic_Index"].max() < n_neurons, "Post-index out of range"

    pre_idx = df_con["Presynaptic_Index"].values
    post_idx = df_con["Postsynaptic_Index"].values
    weights = df_con["Excitatory x Connectivity"].values.astype(np.float64) * W_SYN
    n_exc = (weights > 0).sum()
    n_inh = (weights < 0).sum()
    print(f"  Excitatory edges: {n_exc:,}  Inhibitory edges: {n_inh:,}")
    print(f"  Data loaded in {perf_counter() - t0:.1f}s")
    print()

    # -- Create directory structure --
    net_dir = output_dir / "network"
    comp_dir = output_dir / "components" / "cell_models"
    inp_dir = output_dir / "inputs"
    for d in [net_dir, comp_dir, inp_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # -- Write nodes --
    t1 = perf_counter()
    print("Writing internal nodes...")
    write_internal_nodes(net_dir / "internal_nodes.h5", n_neurons, flywire_ids)
    print(f"  {n_neurons:,} neurons -> internal_nodes.h5")

    n_external = len(stim_indices)
    print("Writing external (virtual) nodes...")
    write_external_nodes(net_dir / "external_nodes.h5", n_external)
    print(f"  {n_external} virtual nodes -> external_nodes.h5")

    # -- Write edges --
    print("Writing internal edges (this may take a moment)...")
    write_internal_edges(net_dir / "internal_internal_edges.h5", pre_idx, post_idx, weights)
    print(f"  {n_edges:,} edges -> internal_internal_edges.h5")

    print("Writing external edges...")
    write_external_edges(net_dir / "external_internal_edges.h5", stim_indices)
    print(f"  {n_external} edges -> external_internal_edges.h5")
    print(f"  Network files written in {perf_counter() - t1:.1f}s")
    print()

    # -- Write type CSVs --
    print("Writing type CSVs and dynamics params...")
    write_node_types_csv(
        net_dir / "internal_node_types.csv",
        node_type_id=0,
        model_template="nest:iaf_psc_alpha",
        dynamics_params="flywire_lif.json",
    )
    write_virtual_node_types_csv(net_dir / "external_node_types.csv")
    write_edge_types_csv(net_dir / "internal_internal_edge_types.csv")
    write_edge_types_csv(net_dir / "external_internal_edge_types.csv")
    write_dynamics_params(comp_dir / "flywire_lif.json")

    # -- Write configs --
    print("Writing circuit and simulation configs...")
    write_circuit_config(output_dir / "circuit_config.json")
    write_simulation_config(output_dir / "simulation_config.json", duration_ms, experiment)
    write_node_sets(output_dir / "node_sets.json", stim_indices, sugar_indices, p9_indices)

    # -- Generate Poisson spike trains --
    print(f"Generating Poisson spikes ({n_external} nodes, {stim_rate} Hz, {duration_ms} ms)...")
    n_spikes = generate_poisson_spikes(
        inp_dir / "poisson_spikes.h5",
        n_nodes=n_external,
        rate_hz=stim_rate,
        duration_ms=duration_ms,
        seed=seed,
    )
    print(f"  {n_spikes:,} spikes -> poisson_spikes.h5")
    print()

    # -- Write FlyWire ID mapping for convenience --
    id_map = pd.DataFrame({
        "node_id": np.arange(n_neurons),
        "flywire_id": flywire_ids,
    })
    id_map.to_csv(net_dir / "flywire_id_map.csv", index=False)

    # -- Summary --
    print("=" * 60)
    print("SONATA circuit written successfully!")
    print("=" * 60)
    print(f"  Output directory:    {output_dir}")
    print(f"  Internal neurons:    {n_neurons:,}")
    print(f"  Synaptic edges:      {n_edges:,}")
    print(f"  Stimulated neurons:  {n_external} ({experiment_name})")
    print(f"  Poisson rate:        {stim_rate} Hz")
    print(f"  Simulation duration: {duration_ms} ms")
    print(f"  Total time:          {perf_counter() - t0:.1f}s")
    print()
    print("Files:")
    for p in sorted(output_dir.rglob("*")):
        if p.is_file():
            size_mb = p.stat().st_size / 1024 / 1024
            rel = p.relative_to(output_dir)
            print(f"  {str(rel):<50s} {size_mb:>8.2f} MB")
    print()
    print("To run with standard NEST:")
    print('  nest.SonataNetwork("circuit_config.json")')
    print()
    print("To run with NEST GPU, see the companion notebook: run_nest_gpu.ipynb")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert FlyWire Drosophila connectome to SONATA circuit format",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent.parent / "fly-brain" / "data",
        help="Path to fly-brain/data directory (default: ../../../fly-brain/data)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "sonata_circuit",
        help="Output directory for SONATA files (default: ./sonata_circuit)",
    )
    parser.add_argument(
        "--experiment",
        choices=list(EXPERIMENTS),
        default="sugar",
        help="Experiment configuration (default: sugar)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=1000.0,
        help="Simulation duration in ms (default: 1000)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for Poisson spike generation (default: 42)",
    )
    args = parser.parse_args()

    if not (args.data_dir / "2025_Completeness_783.csv").exists():
        print(f"ERROR: Completeness CSV not found in {args.data_dir}", file=sys.stderr)
        print("  Provide --data-dir pointing to the fly-brain/data directory.", file=sys.stderr)
        sys.exit(1)

    convert(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        experiment_name=args.experiment,
        duration_ms=args.duration,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()

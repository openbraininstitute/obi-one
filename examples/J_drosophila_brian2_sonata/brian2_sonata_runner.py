"""Minimal Brian2 runner for SONATA circuits.

Prototype wrapper that simulates point-neuron circuits stored in SONATA format
where neuron model equations are carried alongside numeric dynamics_params:

  /nodes/<pop>/0/dynamics_params/
      <numeric_param>   length-N dataset   (one value per node)
      eqs               scalar string      Brian2 differential equations
      eq_th             scalar string      threshold expression
      eq_rst            scalar string      reset statement
      method            scalar string      integration method (default "linear")

  /edges/<pop>/0/
      syn_weight        length-M dataset   per-edge weight (volts, SI)
      delay             length-M dataset   per-edge delay  (seconds, SI)

The simulation_config.json `inputs` entries with module == "poisson" are expanded
into one brian2.PoissonInput per target neuron.

Only enough functionality is implemented here to reproduce a single run_trial
from the philshiu Drosophila_brain_model reference.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np


_VOLT_PARAMS = frozenset({"v_0", "v_rst", "v_th", "E_L", "V_reset", "V_th", "V_m"})
_SECOND_PARAMS = frozenset(
    {"t_mbr", "tau", "tau_m", "tau_syn_ex", "tau_syn_in", "t_ref", "rfc", "t_dly"}
)


def _resolve_manifest_path(path_str: str, manifest: dict, base_dir: Path) -> Path:
    """Resolve $VAR substitutions in a SONATA path string, anchored at base_dir."""
    for var, value in (manifest or {}).items():
        path_str = path_str.replace(f"${var}", value)
    p = Path(path_str)
    if not p.is_absolute():
        p = (base_dir / p).resolve()
    return p


def load_circuit_config(circuit_config_path: str | Path) -> dict:
    cp = Path(circuit_config_path).resolve()
    cfg = json.loads(cp.read_text())
    manifest = cfg.get("manifest", {})
    manifest.setdefault("BASE_DIR", str(cp.parent))
    manifest.setdefault("NETWORK_DIR", str(cp.parent))

    nodes_entries = [
        {
            "nodes_file": _resolve_manifest_path(nd["nodes_file"], manifest, cp.parent),
            "populations": nd.get("populations", {}),
        }
        for nd in cfg["networks"]["nodes"]
    ]
    edges_entries = [
        {
            "edges_file": _resolve_manifest_path(ed["edges_file"], manifest, cp.parent),
            "populations": ed.get("populations", {}),
        }
        for ed in cfg["networks"]["edges"]
    ]
    node_sets_file = cfg.get("node_sets_file")
    if node_sets_file:
        node_sets_file = _resolve_manifest_path(node_sets_file, manifest, cp.parent)
    return {
        "nodes_entries": nodes_entries,
        "edges_entries": edges_entries,
        "node_sets_file": node_sets_file,
        "config_path": cp,
    }


def load_simulation_config(simulation_config_path: str | Path) -> dict:
    sp = Path(simulation_config_path).resolve()
    cfg = json.loads(sp.read_text())
    manifest = cfg.get("manifest", {})
    manifest.setdefault("BASE_DIR", str(sp.parent))

    network_path = _resolve_manifest_path(cfg["network"], manifest, sp.parent)
    node_sets_file = cfg.get("node_sets_file")
    if node_sets_file:
        node_sets_file = _resolve_manifest_path(node_sets_file, manifest, sp.parent)
    return {
        "run": cfg["run"],
        "conditions": cfg.get("conditions", {}),
        "inputs": cfg.get("inputs", {}),
        "network_path": network_path,
        "node_sets_file": node_sets_file,
        "target_simulator": cfg.get("target_simulator", "BRIAN2"),
        "config_path": sp,
    }


def _decode(val: Any) -> Any:
    if isinstance(val, bytes):
        return val.decode()
    return val


def load_node_population(nodes_file: Path, population_name: str) -> dict:
    """Read a single-group point-neuron population into a dict."""
    with h5py.File(nodes_file, "r") as f:
        pop = f[f"nodes/{population_name}"]
        n_nodes = int(pop["node_type_id"].shape[0])
        group_ids = pop["node_group_id"][:]
        if not (group_ids == 0).all():
            err_msg = "Only single-group (all group_id == 0) node populations are supported."
            raise NotImplementedError(err_msg)

        grp0 = pop["0"]
        dynamics = grp0["dynamics_params"]

        per_neuron: dict[str, np.ndarray] = {}
        scalars: dict[str, Any] = {}
        for key in dynamics:
            ds = dynamics[key]
            if ds.shape == ():
                scalars[key] = _decode(ds[()])
            elif ds.shape == (1,):
                scalars[key] = _decode(ds[0])
            else:
                per_neuron[key] = ds[:]

        extras: dict[str, np.ndarray] = {}
        for key in grp0:
            if key == "dynamics_params":
                continue
            ds = grp0[key]
            if isinstance(ds, h5py.Dataset):
                extras[key] = ds[:]

    return {
        "n_nodes": n_nodes,
        "per_neuron_params": per_neuron,
        "scalar_params": scalars,
        "extras": extras,
    }


def load_edge_population(edges_file: Path, population_name: str) -> dict:
    with h5py.File(edges_file, "r") as f:
        pop = f[f"edges/{population_name}"]
        source = pop["source_node_id"][:]
        target = pop["target_node_id"][:]
        group_ids = pop["edge_group_id"][:]
        if not (group_ids == 0).all():
            err_msg = "Only single-group (all group_id == 0) edge populations are supported."
            raise NotImplementedError(err_msg)

        grp0 = pop["0"]
        per_edge: dict[str, np.ndarray] = {}
        scalars: dict[str, Any] = {}
        for key in grp0:
            ds = grp0[key]
            if not isinstance(ds, h5py.Dataset):
                continue
            if ds.shape == ():
                scalars[key] = _decode(ds[()])
            elif ds.shape == (1,):
                scalars[key] = _decode(ds[0])
            else:
                per_edge[key] = ds[:]
    return {
        "n_edges": int(len(source)),
        "source_node_id": source,
        "target_node_id": target,
        "per_edge_params": per_edge,
        "scalar_params": scalars,
    }


def load_node_sets(node_sets_file: Path | None) -> dict:
    if node_sets_file is None:
        return {}
    return json.loads(Path(node_sets_file).read_text())


def resolve_node_set(
    node_set_name: str, node_sets: dict, population_name: str, n_nodes: int
) -> np.ndarray:
    """Resolve a node set name to an array of node indices in the given population."""
    if node_set_name not in node_sets:
        err_msg = f"Node set '{node_set_name}' not found."
        raise KeyError(err_msg)
    spec = node_sets[node_set_name]
    pop_filter = spec.get("population")
    if pop_filter is not None and pop_filter != population_name:
        return np.array([], dtype=int)
    if "node_id" in spec:
        return np.asarray(spec["node_id"], dtype=int)
    return np.arange(n_nodes, dtype=int)


def _infer_unit(param_name: str, ureg: dict) -> Any:
    """Return a brian2 unit for a dynamics_param name based on naming conventions."""
    if param_name in _VOLT_PARAMS:
        return ureg["volt"]
    if param_name in _SECOND_PARAMS:
        return ureg["second"]
    return 1


def run_sonata_brian2_trial(  # noqa: C901, PLR0912, PLR0915
    simulation_config_path: str | Path,
    node_population: str | None = None,
    edge_population: str | None = None,
    seed: int | None = None,
    progress: bool = False,
) -> dict:
    """Run a single Brian2 trial defined by a SONATA simulation config.

    Returns a dict with keys:
        spike_trains: {node_id: spike_time_array_in_seconds}
        n_nodes: number of neurons
        spike_monitor, neuron_group, synapses, network: brian2 objects
    """
    import brian2 as b2  # noqa: PLC0415

    b2.start_scope()
    if seed is not None:
        b2.seed(int(seed))

    ureg = {"volt": b2.volt, "second": b2.second, "Hz": b2.Hz, "ms": b2.ms}

    sim = load_simulation_config(simulation_config_path)
    circ = load_circuit_config(sim["network_path"])

    nodes_entry = circ["nodes_entries"][0]
    edges_entry = circ["edges_entries"][0]
    node_population = node_population or next(iter(nodes_entry["populations"]))
    edge_population = edge_population or next(iter(edges_entry["populations"]))

    node_data = load_node_population(nodes_entry["nodes_file"], node_population)
    edge_data = load_edge_population(edges_entry["edges_file"], edge_population)

    scalars = node_data["scalar_params"]
    if "eqs" not in scalars:
        err_msg = "dynamics_params is missing scalar string 'eqs' (Brian2 equations)."
        raise KeyError(err_msg)
    eqs = scalars["eqs"]
    eq_th = scalars.get("eq_th", "v > v_th")
    eq_rst = scalars.get("eq_rst", "v = v_rst")
    method = scalars.get("method", "linear")

    # Auto-declare per-neuron numeric params that aren't already in the equations string.
    declared = set()
    for line in eqs.splitlines():
        stripped = line.strip()
        if ":" in stripped and not stripped.startswith("d"):
            declared.add(stripped.split(":")[0].strip().split("=")[0].strip())

    extra_decls = []
    for name in node_data["per_neuron_params"]:
        if name in declared:
            continue
        unit = _infer_unit(name, ureg)
        unit_str = (
            "volt" if unit is ureg["volt"] else ("second" if unit is ureg["second"] else "1")
        )
        extra_decls.append(f"{name} : {unit_str} (constant)")
    full_eqs = eqs + ("\n" + "\n".join(extra_decls) if extra_decls else "")

    neu = b2.NeuronGroup(
        N=node_data["n_nodes"],
        model=full_eqs,
        method=method,
        threshold=eq_th,
        reset=eq_rst,
        refractory="rfc" if "rfc" in node_data["per_neuron_params"] else False,
        name="sonata_neurons",
    )

    for name, values in node_data["per_neuron_params"].items():
        unit = _infer_unit(name, ureg)
        setattr(neu, name, values * unit)

    # Initial conditions: membrane potential at v_0, synaptic conductance at 0.
    if "v_0" in node_data["per_neuron_params"]:
        neu.v = node_data["per_neuron_params"]["v_0"] * ureg["volt"]
    if "g" in full_eqs:
        neu.g = 0 * ureg["volt"]

    on_pre = edge_data["scalar_params"].get("on_pre", "g += syn_weight")
    syn_model = edge_data["scalar_params"].get("syn_model", "syn_weight : volt")

    syn = b2.Synapses(neu, neu, model=syn_model, on_pre=on_pre, name="sonata_synapses")
    syn.connect(
        i=edge_data["source_node_id"].astype(int),
        j=edge_data["target_node_id"].astype(int),
    )
    if "syn_weight" in edge_data["per_edge_params"]:
        syn.syn_weight = edge_data["per_edge_params"]["syn_weight"] * ureg["volt"]
    if "delay" in edge_data["per_edge_params"]:
        syn.delay = edge_data["per_edge_params"]["delay"] * ureg["second"]
    elif "delay" in edge_data["scalar_params"]:
        syn.delay = float(edge_data["scalar_params"]["delay"]) * ureg["second"]

    node_sets_path = sim["node_sets_file"] or circ["node_sets_file"]
    node_sets = load_node_sets(node_sets_path)

    poisson_inputs = []
    for inp_name, inp_spec in sim["inputs"].items():
        if inp_spec.get("module") != "poisson":
            if progress:
                print(f"Skipping input '{inp_name}' (module={inp_spec.get('module')!r})")
            continue
        idx = resolve_node_set(
            inp_spec["node_set"], node_sets, node_population, node_data["n_nodes"]
        )
        if len(idx) == 0:
            continue
        rate = float(inp_spec["rate"]) * ureg["Hz"]
        weight = float(inp_spec["weight"]) * ureg["volt"]
        target_var = inp_spec.get("target_var", "v")
        for i in idx:
            ii = int(i)
            p = b2.PoissonInput(
                target=neu[ii : ii + 1],
                target_var=target_var,
                N=1,
                rate=rate,
                weight=weight,
            )
            poisson_inputs.append(p)
            if inp_spec.get("zero_refractory", True) and "rfc" in node_data["per_neuron_params"]:
                neu.rfc[ii] = 0 * ureg["second"]

    spk_mon = b2.SpikeMonitor(neu)
    net = b2.Network(neu, syn, spk_mon, *poisson_inputs)

    tstop_raw = sim["run"]["tstop"]
    tstop = float(tstop_raw) * ureg["ms"] if float(tstop_raw) > 10 else float(tstop_raw) * ureg["second"]  # noqa: PLR2004
    dt = float(sim["run"].get("dt", 0.1)) * ureg["ms"]
    b2.defaultclock.dt = dt

    net.run(duration=tstop, report="text" if progress else None)

    spike_trains = {
        int(k): np.asarray(v / ureg["second"]) for k, v in spk_mon.spike_trains().items() if len(v)
    }
    return {
        "spike_trains": spike_trains,
        "n_nodes": node_data["n_nodes"],
        "spike_monitor": spk_mon,
        "neuron_group": neu,
        "synapses": syn,
        "network": net,
        "node_data": node_data,
        "edge_data": edge_data,
    }

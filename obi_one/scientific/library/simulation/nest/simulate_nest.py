"""Load a SONATA-extension NEST circuit and build/simulate it in NEST through PyNEST.

:class:`NestSonataNetwork` mirrors the stock ``nest.SonataNetwork`` API (``Create`` / ``Connect`` /
``BuildNetwork`` / ``Simulate``) but reads the format described in ``sonata_nest.rst``:
per-population model templates, ``/0/model_template`` and ``/0/dynamics_params`` in the nodes/edges
files, and ``synapse_replay`` spike inputs for virtual populations. NEST needs no SONATA support.

Requires the ``nest`` extra; import this module lazily.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import libsonata
import nest
import numpy as np

from obi_one.scientific.library.simulation.nest import nestml_build
from obi_one.scientific.library.simulation.nest.constants import (
    NODE_TYPES,
    TYPE_CHEMICAL,
    TYPE_VIRTUAL,
    split_model_template,
)
from obi_one.utils.io import load_json

EDGE_WEIGHT = "syn_weight"
EDGE_DELAY = "delay"


def _runs(values: list[str]) -> list[tuple[str, int, int]]:
    """Split *values* into ``(value, start, stop)`` runs of equal consecutive entries."""
    runs = []
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or values[i] != values[start]:
            runs.append((values[start], start, i))
            start = i
    return runs


class NestSonataNetwork:
    def __init__(
        self,
        config: str | Path,
        sim_config: str | Path | None = None,
        num_threads: int = 1,
    ) -> None:
        """Parse the configuration files with ``libsonata``.

        Args:
            config: The ``simulation_config.json`` (its ``network`` points at the circuit config),
                or a ``circuit_config.json`` when *sim_config* is given.
            sim_config: Simulation config to use with a circuit *config*; its ``network`` is
                ignored.
            num_threads: OpenMP threads of the NEST kernel. NEST ignores ``OMP_NUM_THREADS`` and
                runs on one thread unless this is set.
        """
        if num_threads < 1:
            msg = f"num_threads must be at least 1, got {num_threads}."
            raise ValueError(msg)
        self._num_threads = num_threads
        if sim_config is None:
            sim_path = Path(config).resolve(strict=True)
            if "network" not in load_json(sim_path):
                msg = (
                    f"{sim_path} is not a simulation config; pass the simulation_config.json "
                    "(run.dt/run.tstop are required) or a circuit config together with sim_config."
                )
                raise ValueError(msg)
            sim = libsonata.SimulationConfig.from_file(str(sim_path))
            circuit_path = Path(sim.network).resolve(strict=True)
        else:
            sim_path = Path(sim_config).resolve(strict=True)
            sim = libsonata.SimulationConfig.from_file(str(sim_path))
            circuit_path = Path(config).resolve(strict=True)
        circuit = libsonata.CircuitConfig.from_file(str(circuit_path))

        nest_type = libsonata.SimulatorType.NEST
        if circuit.target_simulator != nest_type or sim.target_simulator != nest_type:
            msg = "'target_simulator' in configuration file must be 'NEST'."
            raise ValueError(msg)

        self._circuit = circuit
        self._sim = sim
        self._config_path = circuit_path
        self._base_dir = circuit_path.parent
        if sim.run.random_seed < 0:
            msg = f"run.random_seed must not be negative, got {sim.run.random_seed}."
            raise ValueError(msg)
        self._run = {
            "dt": float(sim.run.dt),
            "tstop": float(sim.run.tstop),
            "random_seed": int(sim.run.random_seed),
        }
        self._node_sets_path = sim.node_sets_file or circuit.node_sets_path

        self._node_populations = self._collect_populations("nodes", NODE_TYPES)
        self._edge_populations = self._collect_populations("edges", {TYPE_CHEMICAL})
        self._templates: dict[Path, dict] = {}
        self._node_collections: dict = {}
        self._are_nodes_created = False
        self._is_network_built = False
        self._nestml_cache_dir = self._base_dir / ".nestml_cache"

    def _collect_populations(self, kind: str, valid_types: set[str] | frozenset[str]) -> dict:
        if kind == "nodes":
            names, properties = (
                self._circuit.node_populations,
                self._circuit.node_population_properties,
            )
        else:
            names, properties = (
                self._circuit.edge_populations,
                self._circuit.edge_population_properties,
            )
        populations = {}
        for pop_name in sorted(names):
            props = properties(pop_name)
            if props.type not in valid_types:
                msg = f"Unsupported {kind[:-1]} population type '{props.type}' for '{pop_name}'."
                raise ValueError(msg)
            populations[pop_name] = {
                "name": pop_name,
                "type": props.type,
                f"{kind}_file": Path(props.elements_path),
                "point_neuron_models_dir": (
                    Path(props.point_neuron_models_dir) if props.point_neuron_models_dir else None
                ),
            }
        return populations

    def load_template(self, population: str, template_name: str) -> dict:
        meta = self._node_populations.get(population) or self._edge_populations[population]
        template_dir = meta["point_neuron_models_dir"]
        if template_dir is None:
            msg = f"Population '{population}' has no point_neuron_models_dir."
            raise ValueError(msg)
        path = template_dir / f"{template_name}.json"
        if path not in self._templates:
            if not path.exists():
                msg = f"Model template '{template_name}' of '{population}' not found at {path}."
                raise FileNotFoundError(msg)
            template = load_json(path)
            if "model" not in template:
                msg = f"Model template {path} has no 'model' entry."
                raise ValueError(msg)
            self._templates[path] = template
        return self._templates[path]

    @property
    def config(self) -> dict:
        """The expanded circuit config, with ``run``/``inputs`` from the simulation config."""
        circuit = json.loads(self._circuit.expanded_json)
        sim = json.loads(self._sim.expanded_json)
        return {**circuit, **{k: sim[k] for k in ("run", "inputs", "target_simulator") if k in sim}}

    @property
    def node_populations(self) -> dict:
        return self._node_populations

    @property
    def edge_populations(self) -> dict:
        return self._edge_populations

    @property
    def node_collections(self) -> dict:
        return self._node_collections

    @property
    def run(self) -> dict:
        return self._run

    @property
    def tstop(self) -> float:
        if "tstop" in self._run:
            return float(self._run["tstop"])
        if "duration" in self._run:
            return float(self._run["duration"])
        msg = "Simulation time 'tstop' or 'duration' must be specified in the configuration file."
        raise ValueError(msg)

    @property
    def dt(self) -> float:
        return float(self._run["dt"])

    @property
    def rng_seed(self) -> int:
        """The NEST seed: ``run.random_seed`` plus one, because NEST rejects a seed of 0."""
        return self._run["random_seed"] + 1

    def _reset_kernel(self) -> None:
        nest.ResetKernel()
        nest.resolution = self.dt
        nest.local_num_threads = self._num_threads
        nest.rng_seed = self.rng_seed

    def Create(self) -> dict:
        self._reset_kernel()
        spike_inputs = self._load_spike_inputs()
        for name, meta in self._node_populations.items():
            population = self._circuit.node_population(name)
            if meta["type"] == TYPE_VIRTUAL:
                collection = self._create_virtual(population, spike_inputs.get(name, {}))
            else:
                collection = self._create_neurons(name, population)
            self._node_collections[name] = collection
        self._are_nodes_created = True
        return self._node_collections

    def _create_neurons(self, name: str, population: libsonata.NodePopulation) -> Any:
        selection = population.select_all()
        if "model_template" not in population.attribute_names:
            msg = f"Node population '{name}' has no /0/model_template dataset."
            raise ValueError(msg)
        templates = list(population.get_attribute("model_template", selection))
        available = population.dynamics_attribute_names
        per_node: dict[str, Any] = {}
        collection = None
        for template_name, start, stop in _runs(templates):
            template = self.load_template(name, template_name)
            model = self._resolve_model_name(name, template["model"])
            created = nest.Create(model, n=stop - start, params=template.get("params") or None)
            for param in template.get("dynamics_params", {}):
                if param not in available:
                    msg = f"'{name}': template '{template_name}' declares missing '{param}'."
                    raise ValueError(msg)
                if param not in per_node:
                    per_node[param] = population.get_dynamics_attribute(param, selection)
                created.set([{param: float(v)} for v in per_node[param][start:stop]])
            collection = created if collection is None else collection + created
        return collection

    @staticmethod
    def _create_virtual(population: libsonata.NodePopulation, spikes: dict) -> Any:
        params = [
            {"spike_times": list(spikes.get(i, [])), "allow_offgrid_times": True}
            for i in range(population.size)
        ]
        return nest.Create("spike_train_injector", n=population.size, params=params)

    def _node_set_members(self, node_set: str) -> dict[str, set[int]]:
        if not self._node_sets_path:
            msg = f"Input targets node set '{node_set}' but no node_sets_file is defined."
            raise ValueError(msg)
        node_sets = libsonata.NodeSets.from_file(self._node_sets_path)
        if node_set not in node_sets.names:
            msg = f"Node set '{node_set}' is not defined in {self._node_sets_path}."
            raise ValueError(msg)
        members = {}
        for pop_name, meta in self._node_populations.items():
            if meta["type"] != TYPE_VIRTUAL:
                continue
            population = self._circuit.node_population(pop_name)
            ids = node_sets.materialize(node_set, population).flatten()
            if len(ids):
                members[pop_name] = {int(i) for i in ids}
        return members

    def _load_spike_inputs(self) -> dict:
        """Read ``synapse_replay`` inputs -> ``{population: {node_id: sorted spike times}}``."""
        replay = libsonata.SimulationConfig.InputBase.Module.synapse_replay
        spikes: dict = {}
        for name in sorted(self._sim.list_input_names):
            spec = self._sim.input(name)
            if spec.module != replay:
                msg = f"Input '{name}': only the 'synapse_replay' module is supported for NEST."
                raise NotImplementedError(msg)
            start = float(spec.delay)
            stop = start + float(spec.duration)
            for pop_name, ids in self._node_set_members(spec.node_set).items():
                with h5py.File(spec.spike_file, "r") as handle:
                    group = handle["spikes"]
                    if pop_name in group and isinstance(group[pop_name], h5py.Group):
                        group = group[pop_name]
                    key = "node_ids" if "node_ids" in group else "gids"
                    node_ids = group[key][:]
                    times = group["timestamps"][:]
                window = (times >= start) & (times < stop)
                node_ids, times = node_ids[window], times[window]
                per_node = spikes.setdefault(pop_name, {})
                for nid in np.unique(node_ids):
                    if int(nid) in ids:
                        per_node[int(nid)] = np.sort(times[node_ids == nid])
        return spikes

    def _resolve_model_name(self, population: str, model_ref: str) -> str:
        """Return the NEST model name for a template's ``model`` (``nest:``/``nestml:`` prefix).

        A ``nestml:<name>`` model is compiled from ``<point_neuron_models_dir>/<name>.nestml`` once
        (cached by source hash) and installed into the kernel.
        """
        backend, model_name = split_model_template(model_ref)
        if backend != "nestml":
            return model_name
        meta = self._node_populations.get(population) or self._edge_populations[population]
        return self._ensure_nestml_model(model_name, meta["point_neuron_models_dir"])

    @staticmethod
    def _nestml_source_path(model_name: str, models_dir: Path | None) -> Path:
        if models_dir is not None:
            candidate = models_dir / f"{model_name}.nestml"
            if candidate.exists():
                return candidate
        msg = f"Could not find NESTML source '{model_name}.nestml' under {models_dir}."
        raise FileNotFoundError(msg)

    def _ensure_nestml_model(self, model_name: str, models_dir: Path | None) -> str:
        source = self._nestml_source_path(model_name, models_dir)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        library = nestml_build.compile_nestml_module(
            source, self._nestml_cache_dir / digest, f"nestml_{digest}module"
        )

        name = self._nestml_model_name(model_name)
        # nest.ResetKernel() unloads installed modules, so reinstall when the model is missing
        if name not in nest.node_models and name not in nest.synapse_models:
            nest.Install(str(library))
            name = self._nestml_model_name(model_name)
        return name

    @staticmethod
    def _nestml_model_name(model_name: str) -> str:
        """Return the NEST model name NESTML registered for *model_name*.

        NESTML commonly suffixes generated models with ``_nestml``; fall back to the bare name.
        """
        suffixed = f"{model_name}_nestml"
        if suffixed in nest.node_models or suffixed in nest.synapse_models:
            return suffixed
        return model_name

    def Connect(self) -> None:
        if not self._are_nodes_created:
            msg = "Nodes must be created before connecting; call Create() first."
            raise RuntimeError(msg)
        for name in self._edge_populations:
            population = self._circuit.edge_population(name)
            self._connect_population(name, population, nest.resolution)
        self._is_network_built = True

    def _connect_population(
        self, name: str, population: libsonata.EdgePopulation, resolution: float
    ) -> None:
        selection = population.select_all()
        if "model_template" not in population.attribute_names:
            msg = f"Edge population '{name}' has no /0/model_template dataset."
            raise ValueError(msg)
        templates = list(population.get_attribute("model_template", selection))
        base_specs, per_edge = self._edge_templates(name, population, set(templates))
        for key in (EDGE_WEIGHT, EDGE_DELAY):
            if key in population.attribute_names:
                per_edge[key] = population.get_attribute(key, selection)
        source_ids = population.source_nodes(selection)
        target_ids = population.target_nodes(selection)
        source_nc = self._node_collections[population.source]
        target_nc = self._node_collections[population.target]
        for i, template_name in enumerate(templates):
            syn_spec = self._edge_syn_spec(base_specs[template_name], per_edge, i)
            if "delay" in syn_spec:
                syn_spec["delay"] = max(float(syn_spec["delay"]), resolution)
            nest.Connect(
                source_nc[int(source_ids[i])], target_nc[int(target_ids[i])], syn_spec=syn_spec
            )

    def _edge_templates(
        self, name: str, population: libsonata.EdgePopulation, template_names: set[str]
    ) -> tuple[dict[str, tuple[dict, list[str]]], dict[str, Any]]:
        """Return ``{template: (base syn_spec, per-edge params)}`` and the per-edge columns."""
        selection = population.select_all()
        available = population.dynamics_attribute_names
        per_edge: dict[str, Any] = {}
        base_specs = {}
        for template_name in template_names:
            template = self.load_template(name, template_name)
            spec = dict(template.get("params", {}))
            model = self._resolve_model_name(name, template["model"])
            if model != "static_synapse":
                spec["synapse_model"] = model
            declared = list(template.get("dynamics_params", {}))
            for param in declared:
                if param not in available:
                    msg = f"'{name}': template '{template_name}' declares missing '{param}'."
                    raise ValueError(msg)
                if param not in per_edge:
                    per_edge[param] = population.get_dynamics_attribute(param, selection)
            base_specs[template_name] = (spec, declared)
        return base_specs, per_edge

    @staticmethod
    def _edge_syn_spec(base: tuple[dict, list[str]], per_edge: dict, i: int) -> dict:
        """Build edge *i*'s ``syn_spec``: params, then ``syn_weight``/``delay``, then dynamics."""
        spec, declared = base
        syn_spec = dict(spec)
        if EDGE_WEIGHT in per_edge:
            syn_spec["weight"] = float(per_edge[EDGE_WEIGHT][i])
        if EDGE_DELAY in per_edge:
            syn_spec["delay"] = float(per_edge[EDGE_DELAY][i])
        for param in declared:
            value = per_edge[param][i]
            syn_spec[param] = int(value) if param == "receptor_type" else float(value)
        return syn_spec

    def BuildNetwork(self) -> dict:
        node_collections = self.Create()
        self.Connect()
        return node_collections

    def add_spike_recorders(self) -> dict:
        if not self._are_nodes_created:
            msg = "Nodes must be created before adding recorders; call Create() first."
            raise RuntimeError(msg)
        recorders = {}
        for name, meta in self._node_populations.items():
            if meta["type"] == TYPE_VIRTUAL:
                continue
            recorder = nest.Create("spike_recorder")
            nest.Connect(self._node_collections[name], recorder)
            recorders[name] = recorder
        return recorders

    def Simulate(self) -> None:
        if not self._is_network_built:
            msg = "The network must be built before simulating; call BuildNetwork() first."
            raise RuntimeError(msg)
        nest.Simulate(self.tstop)

    @property
    def spikes_file(self) -> Path:
        return Path(self._sim.output.spikes_file)

    @property
    def report_names(self) -> set[str]:
        return set(self._sim.list_report_names)

    def write_spike_report(self, recorders: dict, path: str | Path | None = None) -> Path:
        """Write the spikes of *recorders* as a SONATA spike report, sorted by time.

        Args:
            recorders: ``{population: spike_recorder}``, as returned by :meth:`add_spike_recorders`.
            path: Output HDF5 file; defaults to :attr:`spikes_file`.

        Returns:
            The path of the written report. Node ids are the SONATA ids within each population.
        """
        path = Path(path) if path is not None else self.spikes_file
        path.parent.mkdir(parents=True, exist_ok=True)
        sorting = h5py.enum_dtype({"none": 0, "by_id": 1, "by_time": 2})
        with h5py.File(path, "w") as handle:
            spikes = handle.create_group("spikes")
            for name, recorder in sorted(recorders.items()):
                events = recorder.get("events")
                gids = np.asarray(self._node_collections[name].tolist(), dtype=np.int64)
                senders = np.asarray(events["senders"], dtype=np.int64)
                times = np.asarray(events["times"], dtype=np.float64)
                node_ids = np.searchsorted(gids, senders)  # NEST ids increase with SONATA ids
                order = np.lexsort((node_ids, times))
                group = spikes.create_group(name)
                group.attrs.create("sorting", data=2, dtype=sorting)
                timestamps = group.create_dataset("timestamps", data=times[order])
                timestamps.attrs["units"] = "ms"
                group.create_dataset("node_ids", data=node_ids[order].astype(np.uint64))
        return path


def run_simulation(simulation_config: str | Path, num_threads: int = 1) -> Path:
    """Build and simulate the circuit of *simulation_config*; write and return its spike report.

    Spikes of every non-virtual population go to the config's ``output.spikes_file``. Voltage
    ``reports`` are not supported by the NEST loader and raise ``NotImplementedError``. NEST runs
    on *num_threads* threads.
    """
    network = NestSonataNetwork(simulation_config, num_threads=num_threads)
    if network.report_names:
        msg = (
            f"Reports {sorted(network.report_names)} are not supported for NEST simulations; "
            "only spikes are recorded."
        )
        raise NotImplementedError(msg)
    network.BuildNetwork()
    recorders = network.add_spike_recorders()
    network.Simulate()
    return network.write_spike_report(recorders)

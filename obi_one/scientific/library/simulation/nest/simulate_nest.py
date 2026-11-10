"""Load a SONATA-extension NEST circuit and build/simulate it in NEST through PyNEST.

:class:`NestSonataNetwork` mirrors the stock ``nest.SonataNetwork`` API (``Create`` / ``Connect`` /
``BuildNetwork`` / ``Simulate``) but reads the format described in ``sonata_nest.rst``:
per-population model templates, ``/0/model_template`` and ``/0/dynamics_params`` in the nodes/edges
files, and ``synapse_replay`` spike inputs for virtual populations. NEST needs no SONATA support.

Requires the ``nest`` extra; import this module lazily.
"""

import hashlib
import importlib.metadata
import json
import logging
import re
from pathlib import Path
from typing import Any

import h5py
import libsonata
import nest
import numpy as np

from obi_one.scientific.library.simulation.nest import (
    connection_overrides,
    current_clamps,
    nestml_build,
    soma_reports,
)
from obi_one.scientific.library.simulation.nest.constants import (
    IGNORED_KEYS,
    NODE_TYPES,
    TYPE_NEST_CHEMICAL,
    TYPE_VIRTUAL,
    split_model_template,
)
from obi_one.scientific.library.simulation.neuron.schemas import SimulationResults
from obi_one.utils.io import load_json

L = logging.getLogger(__name__)

EDGE_WEIGHT = "syn_weight"
EDGE_DELAY = "delay"
EDGE_WEIGHT_PARAM = "weight"
CONNECTION_ID = ("source", "target", "target_thread", "synapse_id", "port")

MODULE = libsonata.SimulationConfig.InputBase.Module
CLAMP_MODULES = (MODULE.linear, MODULE.pulse, MODULE.sinusoidal)

VERSION_PATTERN = re.compile(r"\d+\.\d+")


def minor_version(version: str) -> str:
    match = VERSION_PATTERN.match(str(version))
    return match.group(0) if match else str(version)


def version_warnings(
    provenance: dict, nest_version: str | None = None, nestml_version: str | None = None
) -> list[str]:
    """Warnings for the NEST and NESTML in use that differ from the circuit's ``provenance``.

    Versions are compared by major and minor number. A version that is ``None`` is not checked.
    A missing ``nest_version`` is reported; a missing ``nestml_version`` is not, as it is optional.
    """
    warnings = []
    if nest_version is not None and "nest_version" not in provenance:
        warnings.append(
            f"The circuit config has no components.provenance.nest_version; NEST {nest_version} "
            "is in use."
        )
    for key, name, running in (
        ("nest_version", "NEST", nest_version),
        ("nestml_version", "NESTML", nestml_version),
    ):
        recorded = provenance.get(key)
        if recorded is None or running is None:
            continue
        if minor_version(recorded) != minor_version(running):
            warnings.append(
                f"The circuit was built for {name} {recorded}, but {name} {running} is in use; "
                "parameter names and defaults may differ."
            )
    return warnings


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
        self._edge_populations = self._collect_populations("edges", {TYPE_NEST_CHEMICAL})
        self._templates: dict[Path, dict] = {}
        self._node_collections: dict = {}
        self._are_nodes_created = False
        self._is_network_built = False
        self._nestml_cache_dir = self._base_dir / ".nestml_cache"
        self._provenance = (
            json.loads(circuit.expanded_json).get("components", {}).get("provenance", {})
        )
        self._nestml_version_checked = False
        self._node_sets: libsonata.NodeSets | None = None
        self._replay_collections: dict = {}
        self._replay_nodes: dict = {}
        self._current_generators: dict = {}
        self._report_recorders: dict = {}
        self._base_weights: dict = {}
        raw = json.loads(sim.expanded_json)
        self._warn_ignored(raw)
        self._overrides = connection_overrides.parse_overrides(
            raw.get("connection_overrides", []), self.dt
        )
        self._reports = self._check_reports()
        for message in version_warnings(self._provenance, nest.__version__):
            L.warning(message)

    @staticmethod
    def _warn_ignored(raw: dict) -> None:
        for path in IGNORED_KEYS:
            section = raw
            for key in path[:-1]:
                section = section.get(key, {})
            if path[-1] in section:
                L.warning("'%s' is ignored by NEST.", ".".join(path))
        for name, spec in raw.get("inputs", {}).items():
            if "represents_physical_electrode" in spec:
                L.warning("Input '%s': 'represents_physical_electrode' is ignored by NEST.", name)

    def _check_reports(self) -> dict[str, soma_reports.Frames]:
        """The frames of each enabled report; only soma reports of ``v`` are supported."""
        report_type = libsonata.SimulationConfig.Report
        frames = {}
        for name in sorted(self._sim.list_report_names):
            report = self._sim.report(name)
            if not report.enabled:
                continue
            if (
                report.type != report_type.Type.compartment
                or report.sections != report_type.Sections.soma
                or report.variable_name != "v"
                or report.compartment_set
            ):
                msg = (
                    f"Report '{name}': NEST supports only 'compartment' reports of the 'soma' "
                    "with 'variable_name' 'v'."
                )
                raise NotImplementedError(msg)
            end = min(float(report.end_time), self.tstop)
            frames[name] = soma_reports.Frames.of(
                name, float(report.start_time), end, float(report.dt), self.dt
            )
        return frames

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
        return int(self._run["random_seed"]) + 1

    def _reset_kernel(self) -> None:
        nest.ResetKernel()
        nest.resolution = self.dt
        nest.local_num_threads = self._num_threads
        nest.rng_seed = self.rng_seed

    def Create(self) -> dict:
        self._reset_kernel()
        self._replay_collections = {}
        for name, meta in self._node_populations.items():
            if meta["type"] == TYPE_VIRTUAL:
                continue
            population = self._circuit.node_population(name)
            self._node_collections[name] = self._create_neurons(name, population)
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
            self._check_template_parameters(name, template_name, template, model)
            created = nest.Create(model, n=stop - start, params=template.get("params") or None)
            for param in template.get("dynamics_params", {}):
                if param not in available:
                    msg = f"'{name}': template '{template_name}' declares missing '{param}'."
                    raise ValueError(msg)
                if param not in per_node:
                    per_node[param] = self.read_dynamics(name, population, param, selection)
                created.set([{param: float(v)} for v in per_node[param][start:stop]])
            collection = created if collection is None else collection + created
        return collection

    @staticmethod
    def read_dynamics(name: str, population: Any, param: str, selection: Any) -> np.ndarray:
        """The values of ``/0/dynamics_params/<param>``: one per node or edge, and 1-D."""
        try:
            values = np.asarray(population.get_dynamics_attribute(param, selection))
        except (libsonata.SonataError, RuntimeError) as error:
            msg = (
                f"'{name}': cannot read /0/dynamics_params/{param}: {error}. The datasets of "
                "dynamics_params are 1-D, with one value per node or edge. A list-valued "
                "parameter, such as tau_syn or E_rev of a multisynapse model, goes in the "
                "'params' of the template."
            )
            raise ValueError(msg) from error
        if param == "receptor_type" and not np.array_equal(values, np.round(values)):
            msg = f"'{name}': /0/dynamics_params/receptor_type must hold integers."
            raise ValueError(msg)
        return values

    @property
    def replay_collections(self) -> dict:
        """The injectors of each replay, ``{(input, spike file population): NodeCollection}``."""
        return self._replay_collections

    def _node_set_ids(self, node_set: str, population: str) -> np.ndarray:
        """The ids of *population* in *node_set*."""
        if not self._node_sets_path:
            msg = f"Input targets node set '{node_set}' but no node_sets_file is defined."
            raise ValueError(msg)
        if self._node_sets is None:
            self._node_sets = libsonata.NodeSets.from_file(self._node_sets_path)
        if node_set not in self._node_sets.names:
            msg = f"Node set '{node_set}' is not defined in {self._node_sets_path}."
            raise ValueError(msg)
        selection = self._node_sets.materialize(node_set, self._circuit.node_population(population))
        return np.asarray(selection.flatten(), dtype=np.int64)

    def _replay_spikes(self, name: str, spec: Any) -> dict[str, dict[int, np.ndarray]]:
        """The spikes of a ``synapse_replay`` input in ``[delay, delay + duration)``.

        Returns ``{population: {node_id: sorted spike times}}``. The times are not shifted.
        """
        start = float(spec.delay)
        stop = start + float(spec.duration)
        reader = libsonata.SpikeReader(spec.spike_file)
        spikes = {}
        for population in reader.get_population_names():
            if population not in self._node_populations:
                msg = f"Input '{name}': spike population '{population}' is not a node population."
                raise ValueError(msg)
            data = reader[population].get_dict()
            node_ids = np.asarray(data["node_ids"], dtype=np.int64)
            times = np.asarray(data["timestamps"], dtype=np.float64)
            size = self._circuit.node_population(population).size
            if len(node_ids) and node_ids.max() >= size:
                msg = (
                    f"Input '{name}': spike node id {node_ids.max()} is not in population "
                    f"'{population}', which has {size} nodes."
                )
                raise ValueError(msg)
            window = (times >= start) & (times < stop)
            node_ids, times = node_ids[window], times[window]
            if not len(node_ids):
                L.warning(
                    "Input '%s': no spikes of '%s' in [%s, %s) ms.", name, population, start, stop
                )
                spikes[population] = {}
                continue
            order = np.lexsort((times, node_ids))
            node_ids, times = node_ids[order], times[order]
            unique, first = np.unique(node_ids, return_index=True)
            spikes[population] = {
                int(node): chunk
                for node, chunk in zip(unique, np.split(times, first[1:]), strict=True)
            }
        return spikes

    def _connect_inputs(self) -> None:
        replay = libsonata.SimulationConfig.InputBase.Module.synapse_replay
        covered = set()
        for name in sorted(self._sim.list_input_names):
            spec = self._sim.input(name)
            if spec.module in CLAMP_MODULES:
                self._connect_current_clamp(name, spec)
                continue
            if spec.module != replay:
                msg = (
                    f"Input '{name}': NEST supports the 'linear', 'pulse', 'sinusoidal' and "
                    "'synapse_replay' modules."
                )
                raise NotImplementedError(msg)
            for population, spikes in self._replay_spikes(name, spec).items():
                covered.add(population)
                if spikes:
                    self._replay_population(name, spec, population, spikes)
        for edge_name in self._edge_populations:
            source = self._circuit.edge_population(edge_name).source
            if self._node_populations[source]["type"] == TYPE_VIRTUAL and source not in covered:
                L.warning(
                    "Virtual population '%s' has no synapse_replay input, so its edges carry no "
                    "spikes.",
                    source,
                )

    def _connect_current_clamp(self, name: str, spec: Any) -> None:
        """Inject the current of a ``linear``, ``pulse`` or ``sinusoidal`` input into its nodes."""
        nest_ids = []
        for population, collection in self._node_collections.items():
            ids = self._node_set_ids(spec.node_set, population)
            nest_ids.extend(np.asarray(collection.tolist(), dtype=np.int64)[ids])
        if not nest_ids:
            msg = f"Input '{name}': node set '{spec.node_set}' contains no nest_point node."
            raise ValueError(msg)
        dt = self.dt
        window = current_clamps.Window.of(float(spec.delay), float(spec.duration), dt)
        if window.is_empty:
            L.warning("Input '%s': its window contains no step.", name)
            return
        if spec.module == MODULE.sinusoidal:
            parameters = current_clamps.sinusoidal_parameters(
                float(spec.amp_start), float(spec.frequency), window, dt
            )
            generator = nest.Create("ac_generator", params=parameters)
        elif spec.module == MODULE.linear and spec.amp_end == spec.amp_start:
            generator = nest.Create(
                "dc_generator",
                params={
                    "amplitude": float(spec.amp_start) * current_clamps.NA_TO_PA,
                    "start": round((window.start - 1) * dt, 6),
                    "stop": round((window.end - 1) * dt, 6),
                },
            )
        else:
            if spec.module == MODULE.linear:
                steps = current_clamps.linear_steps(
                    float(spec.amp_start), float(spec.amp_end), window
                )
            else:
                steps = current_clamps.pulse_steps(
                    float(spec.amp_start),
                    float(spec.width),
                    float(spec.frequency),
                    float(spec.delay),
                    window,
                    dt,
                )
            parameters = current_clamps.step_current(steps, dt)
            generator = nest.Create("step_current_generator", params=parameters)
        nest.Connect(generator, nest.NodeCollection(sorted(nest_ids)), "all_to_all", {"delay": dt})
        self._current_generators[name] = generator

    def _replay_population(
        self, name: str, spec: Any, population: str, spikes: dict[int, np.ndarray]
    ) -> None:
        """Deliver *spikes* of *population* through its edges to the targets in the node set."""
        sources = sorted(spikes)
        plan = []
        for edge_name in self._edge_populations:
            edges = self._circuit.edge_population(edge_name)
            if edges.source != population:
                continue
            targets = self._node_set_ids(spec.node_set, edges.target)
            everything = edges.select_all()
            source_ids = np.asarray(edges.source_nodes(everything), dtype=np.int64)
            target_ids = np.asarray(edges.target_nodes(everything), dtype=np.int64)
            indices = np.flatnonzero(np.isin(source_ids, sources) & np.isin(target_ids, targets))
            if len(indices):
                selection = libsonata.Selection(values=indices)
                plan.append((edge_name, edges, selection, source_ids[indices]))
        if not plan:
            msg = (
                f"Input '{name}': node set '{spec.node_set}' contains no target of the edges "
                f"that leave '{population}', so the input delivers nothing."
            )
            raise ValueError(msg)
        used = np.unique(np.concatenate([source_ids for *_, source_ids in plan]))
        injectors = nest.Create(
            "spike_train_injector",
            n=len(used),
            params=[
                {"spike_times": spikes[int(node)].tolist(), "allow_offgrid_times": True}
                for node in used
            ],
        )
        self._replay_collections[name, population] = injectors
        self._replay_nodes[name, population] = used
        injector_ids = np.asarray(injectors.tolist(), dtype=np.int64)
        for edge_name, edges, selection, source_ids in plan:
            self._connect_edges(
                edge_name,
                edges,
                selection,
                injector_ids[np.searchsorted(used, source_ids)],
                self._target_ids(edges, selection),
            )

    @staticmethod
    def _check_template_parameters(
        population: str, template_name: str, template: dict, model: str
    ) -> None:
        """Raise if the template names a parameter that the NEST *model* does not have."""
        names = {*template.get("params", {}), *template.get("dynamics_params", {})}
        available = set(nest.GetDefaults(model))
        unknown = sorted(names - available)
        if unknown:
            msg = (
                f"'{population}': template '{template_name}' has parameters {unknown} that the "
                f"NEST model '{model}' does not have. It has: {sorted(available)}."
            )
            raise ValueError(msg)

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
        if not self._nestml_version_checked:
            self._nestml_version_checked = True
            nestml_version = importlib.metadata.version("nestml")
            for message in version_warnings(self._provenance, None, nestml_version):
                L.warning(message)
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
            if self._node_populations[population.target]["type"] == TYPE_VIRTUAL:
                msg = f"Edge population '{name}' targets virtual population '{population.target}'."
                raise ValueError(msg)
            if self._node_populations[population.source]["type"] == TYPE_VIRTUAL:
                continue  # carried by the synapse_replay inputs
            selection = population.select_all()
            source_ids = np.asarray(
                self._node_collections[population.source].tolist(), dtype=np.int64
            )[population.source_nodes(selection)]
            self._connect_edges(
                name, population, selection, source_ids, self._target_ids(population, selection)
            )
        self._connect_inputs()
        self._is_network_built = True

    def _target_ids(self, population: libsonata.EdgePopulation, selection: Any) -> np.ndarray:
        """The NEST ids of the targets of the edges in *selection*."""
        nest_ids = np.asarray(self._node_collections[population.target].tolist(), dtype=np.int64)
        return nest_ids[population.target_nodes(selection)]

    def _connect_edges(
        self,
        name: str,
        population: libsonata.EdgePopulation,
        selection: Any,
        source_ids: np.ndarray,
        target_ids: np.ndarray,
    ) -> None:
        """Connect the edges in *selection* from the NEST nodes *source_ids* to *target_ids*.

        There is one ``nest.Connect`` call per model template, with the per-edge values as arrays.
        """
        if "model_template" not in population.attribute_names:
            msg = f"Edge population '{name}' has no /0/model_template dataset."
            raise ValueError(msg)
        templates = np.asarray(population.get_attribute("model_template", selection))
        base_specs, per_edge = self._edge_templates(name, population, set(templates), selection)
        for key in (EDGE_WEIGHT, EDGE_DELAY):
            if key in population.attribute_names:
                per_edge[key] = np.asarray(population.get_attribute(key, selection), dtype=float)
        for template_name in np.unique(templates):
            edges = np.flatnonzero(templates == template_name)
            syn_spec = self._batch_syn_spec(
                base_specs[str(template_name)], per_edge, edges, nest.resolution
            )
            nest.Connect(source_ids[edges], target_ids[edges], "one_to_one", syn_spec)

    def _edge_templates(
        self,
        name: str,
        population: libsonata.EdgePopulation,
        template_names: set[str],
        selection: Any,
    ) -> tuple[dict[str, tuple[dict, list[str]]], dict[str, Any]]:
        """Return ``{template: (base syn_spec, per-edge params)}`` and the per-edge columns."""
        available = population.dynamics_attribute_names
        per_edge: dict[str, Any] = {}
        base_specs = {}
        for template_name in template_names:
            template = self.load_template(name, template_name)
            spec = dict(template.get("params", {}))
            model = self._resolve_model_name(name, template["model"])
            self._check_template_parameters(name, template_name, template, model)
            if model != "static_synapse":
                spec["synapse_model"] = model
            declared = list(template.get("dynamics_params", {}))
            for param in declared:
                if param not in available:
                    msg = f"'{name}': template '{template_name}' declares missing '{param}'."
                    raise ValueError(msg)
                if param not in per_edge:
                    per_edge[param] = self.read_dynamics(name, population, param, selection)
            base_specs[template_name] = (spec, declared)
        return base_specs, per_edge

    @staticmethod
    def _batch_syn_spec(
        base: tuple[dict, list[str]], per_edge: dict, edges: np.ndarray, resolution: float
    ) -> dict:
        """The ``syn_spec`` of the *edges* of a template: params, weight and delay, then dynamics.

        NEST connects arrays of nodes only if ``weight`` and ``delay`` are both arrays, so a
        missing one is taken from the synapse model. A delay shorter than the resolution is raised
        to it.
        """
        spec, declared = base
        syn_spec = dict(spec)
        if EDGE_WEIGHT in per_edge:
            syn_spec[EDGE_WEIGHT_PARAM] = per_edge[EDGE_WEIGHT][edges]
        if EDGE_DELAY in per_edge:
            syn_spec[EDGE_DELAY] = per_edge[EDGE_DELAY][edges]
        for param in declared:
            values = np.asarray(per_edge[param])[edges]
            syn_spec[param] = values.astype(np.int64 if param == "receptor_type" else float)
        defaults = nest.GetDefaults(syn_spec.get("synapse_model", "static_synapse"))
        for key in (EDGE_WEIGHT_PARAM, EDGE_DELAY):
            value = np.asarray(syn_spec.get(key, defaults[key]), dtype=float)
            syn_spec[key] = np.array(np.broadcast_to(value, len(edges)))
        syn_spec[EDGE_DELAY] = np.maximum(syn_spec[EDGE_DELAY], resolution)
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
        if not self._overrides:
            nest.Simulate(self.tstop)
            return
        last = round(self.tstop / self.dt)
        self._prepare_overrides()
        now = 0
        for step, group in connection_overrides.schedule(self._overrides, last):
            if step > now:
                nest.Simulate(round((step - now) * self.dt, 6))
                now = step
            for override in group:
                self._apply_override(override)
        nest.Simulate(round((last - now) * self.dt, 6))

    def _override_synapses(self, override: connection_overrides.Override) -> Any:
        """The NEST connections that *override* acts on, including those of the replays."""
        sources, targets = [], []
        for population in self._node_populations:
            ids = self._node_set_ids(override.source, population)
            if population in self._node_collections:
                nest_ids = np.asarray(self._node_collections[population].tolist(), dtype=np.int64)
                sources.extend(nest_ids[ids])
            for key, nodes in self._replay_nodes.items():
                if key[1] == population:
                    injectors = np.asarray(self._replay_collections[key].tolist(), dtype=np.int64)
                    sources.extend(injectors[np.isin(nodes, ids)])
        for population, collection in self._node_collections.items():
            ids = self._node_set_ids(override.target, population)
            targets.extend(np.asarray(collection.tolist(), dtype=np.int64)[ids])
        if not sources or not targets:
            return None
        return nest.GetConnections(
            source=nest.NodeCollection(sorted({int(i) for i in sources})),
            target=nest.NodeCollection(sorted({int(i) for i in targets})),
        )

    def _prepare_overrides(self) -> None:
        """Select the synapses of each override and make room for its delay, before NEST starts.

        NEST fixes the range of the delays at the first simulation. Setting a delay widens it, so
        each ``synapse_delay_override`` is set and restored on its synapses.
        """
        self._selected: dict[int, Any] = {}
        for override in self._overrides:
            synapses = self._override_synapses(override)
            if synapses is None or not len(synapses):
                L.warning("connection_overrides '%s' acts on no synapse.", override.name)
                continue
            self._selected[override.index] = synapses
            if override.synapse_delay is not None:
                original = np.atleast_1d(synapses.get("delay")).tolist()
                synapses.set(delay=override.synapse_delay)
                synapses.set(delay=original)

    def _apply_override(self, override: connection_overrides.Override) -> None:
        synapses = self._selected.get(override.index)
        if synapses is None:
            return
        if override.weight is not None:
            columns = synapses.get(list(CONNECTION_ID))
            ids = np.column_stack([np.atleast_1d(columns[key]) for key in CONNECTION_ID])
            current = np.atleast_1d(synapses.get("weight"))
            circuit = [
                self._base_weights.setdefault(tuple(row), weight)
                for row, weight in zip(ids.tolist(), current, strict=True)
            ]
            synapses.set(weight=(override.weight * np.asarray(circuit)).tolist())
        if override.synapse_delay is not None:
            synapses.set(delay=override.synapse_delay)

    def add_report_recorders(self) -> dict:
        """Connect a multimeter to the nodes of each report; call before :meth:`Simulate`."""
        if not self._are_nodes_created:
            msg = "Nodes must be created before adding recorders; call Create() first."
            raise RuntimeError(msg)
        for name, frames in self._reports.items():
            cells = self._sim.report(name).cells
            recorded = {}
            for population, collection in self._node_collections.items():
                size = self._circuit.node_population(population).size
                ids = self._node_set_ids(cells, population) if cells else np.arange(size)
                if not len(ids):
                    continue
                nest_ids = np.asarray(collection.tolist(), dtype=np.int64)[ids]
                nodes = nest.NodeCollection(nest_ids.tolist())
                try:
                    initial = np.atleast_1d(nodes.get("V_m")).astype(float)
                    multimeter = None
                    if frames.sampled:
                        multimeter = nest.Create(
                            "multimeter", params={"record_from": ["V_m"], **frames.multimeter()}
                        )
                        nest.Connect(multimeter, nodes)
                except (nest.NESTError, KeyError) as error:
                    msg = f"Report '{name}': the model of '{population}' has no V_m ({error})."
                    raise ValueError(msg) from error
                recorded[population] = (multimeter, nest_ids, ids, initial)
            self._report_recorders[name] = recorded
        return self._report_recorders

    def write_reports(self) -> list[Path]:
        """Write the soma reports; return their paths. Call after :meth:`Simulate`."""
        if any(m is not None for rec in self._report_recorders.values() for m, *_ in rec.values()):
            # a multimeter delivers its samples one minimum delay late; this reaches the last one
            nest.Simulate(nest.min_delay)
        paths = []
        for name, recorded in self._report_recorders.items():
            frames = self._reports[name]
            populations = {}
            for population, (multimeter, nest_ids, ids, initial) in recorded.items():
                events = multimeter.get("events") if multimeter is not None else {}
                values = soma_reports.frames_matrix(events, nest_ids, initial, frames)
                populations[population] = (ids, values)
            path = Path(self._sim.report(name).file_name)
            soma_reports.write_soma_report(path, populations, frames)
            paths.append(path)
        return paths

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
                within = times <= self.tstop + 1e-9
                senders, times = senders[within], times[within]
                node_ids = np.searchsorted(gids, senders)  # NEST ids increase with SONATA ids
                order = np.lexsort((node_ids, times))
                group = spikes.create_group(name)
                group.attrs.create("sorting", data=2, dtype=sorting)
                timestamps = group.create_dataset("timestamps", data=times[order])
                timestamps.attrs["units"] = "ms"
                group.create_dataset("node_ids", data=node_ids[order].astype(np.uint64))
        return path


def run_simulation(simulation_config: str | Path, num_threads: int = 1) -> SimulationResults:
    """Build and simulate the circuit of *simulation_config*; write and return its reports.

    Spikes of every non-virtual population go to the config's ``output.spikes_file``, and each
    enabled report is written as a SONATA soma report to its ``file_name``. NEST runs on
    *num_threads* threads.
    """
    network = NestSonataNetwork(simulation_config, num_threads=num_threads)
    network.BuildNetwork()
    recorders = network.add_spike_recorders()
    network.add_report_recorders()
    network.Simulate()
    spike_report = network.write_spike_report(recorders)
    return SimulationResults(
        spike_report_file=spike_report, voltage_report_files=network.write_reports()
    )

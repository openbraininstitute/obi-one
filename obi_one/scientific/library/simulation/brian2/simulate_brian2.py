#!/usr/bin/env python3
# ruff: noqa: S101
import contextlib
import heapq
import logging
import math
import os
import re
import tempfile
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timezone
from functools import partial, singledispatch
from pathlib import Path

import bluepysnap
import bluepysnap.frame_report
import bluepysnap.input
import brian2
import brian2.units
import click
import h5py
import libsonata
import numpy as np
from entitysdk import Client, ProjectContext, models
from entitysdk.models.activity import Activity
from entitysdk.staging import stage_simulation
from entitysdk.token_manager import TokenFromFunction
from entitysdk.types import ActivityStatus, AssetLabel, ContentType
from entitysdk.utils.store import LocalAssetStore
from obi_auth import get_token
from obi_auth.typedef import AuthMode, DeploymentEnvironment
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

REQUIRED_PATH = click.Path(exists=True, readable=True, dir_okay=False, resolve_path=True)
L = logging.getLogger(__name__)
KNOWN_UNITS = {u for u in dir(brian2.units) if not u.startswith("_")}


class Event(BaseModel):
    at: float  # time during the simulation that Event fires (in ms)
    func: Callable  # function to call at time `at`

    def __lt__(self, other: "Event") -> bool:
        """The at which the event should fire is used to sort in the heapq."""
        return self.at < other.at


class Brian2Network(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    neurons: brian2.NeuronGroup
    synapses: brian2.Synapses
    spike_monitor: brian2.SpikeMonitor
    state_monitor: brian2.StateMonitor | None
    inputs: list
    report_id_mapping: np.ndarray
    events: list[Event]


class CurrentStimulator(ABC):
    def __init__(self, config: libsonata.SimulationConfig.InputBase) -> None:
        """Ibid."""
        if config.compartment_set:
            msg = "`compartment_set` not supported"
            raise RuntimeError(msg)
        self.config = config

    def get_selection(
        self, node_sets: libsonata.NodeSets, population: libsonata.NodePopulation
    ) -> libsonata.Selection:
        """Return the selection of neurons from `population` that this stimulus applies to."""
        if self.config.node_set == "All":
            return population.select_all()
        return node_sets.materialize(self.config.node_set, population)

    def get_currents(self, dt: float, simulation_length: float) -> brian2.TimedArray:
        v = self._get_currents(dt, simulation_length)
        return brian2.TimedArray(v * brian2.units.mA, dt=dt * brian2.units.ms)

    @abstractmethod
    def _get_currents(self, dt: float, simulation_length: float) -> np.ndarray:
        pass


class Linear(CurrentStimulator):
    """A continuous linear injection of current."""

    def _get_currents(self, dt: float, simulation_length: float) -> np.ndarray:
        n_total = math.ceil(simulation_length / dt) + 1
        ret = np.zeros(n_total, dtype=np.float32)
        n_delay = math.ceil(self.config.delay / dt)
        if self.config.delay + self.config.duration <= simulation_length:
            n_ramp = math.ceil((self.config.delay + self.config.duration) / dt) + 1
            amp_end = self.config.amp_end
        else:
            n_ramp = math.ceil((simulation_length - self.config.delay) / dt) + 1
            amp_end = self.config.amp_start + (
                simulation_length - self.config.delay
            ) / self.config.duration * (self.config.amp_end - self.config.amp_start)

        n_ramp = min(n_ramp, n_total - n_delay)
        ret[n_delay : (n_delay + n_ramp)] = np.linspace(self.config.amp_start, amp_end, n_ramp)
        return ret


class Pulse(CurrentStimulator):
    """Series of current pulse injections."""

    def _get_currents(self, dt: float, simulation_length: float) -> np.ndarray:
        n_total = math.ceil(simulation_length / dt) + 1
        ret = np.zeros(n_total, dtype=np.float32)

        n_delay = math.ceil(self.config.delay / dt)
        n_end = min(math.ceil((self.config.delay + self.config.duration) / dt), n_total)
        pulse_samples = math.ceil(self.config.width / dt)
        period_samples = math.ceil(1.0 / (self.config.frequency * dt))

        for start in range(n_delay, n_end, period_samples):
            end = min(start + pulse_samples, n_end)
            ret[start:end] = self.config.amp_start

        return ret


class Sinusoidal(CurrentStimulator):
    """A generated sinusoidal current."""

    def _get_currents(self, dt: float, simulation_length: float) -> np.ndarray:
        assert dt == self.config.dt, f"simulation dt: {dt} != input dt: {self.config.dt}"

        n_total = math.ceil(simulation_length / dt) + 1
        ret = np.zeros(n_total, dtype=np.float32)

        n_delay = math.ceil(self.config.delay / dt)
        n_end = min(math.ceil((self.config.delay + self.config.duration) / dt), n_total)

        t = np.arange(n_end - n_delay) * dt
        ret[n_delay:n_end] = self.config.amp_start * np.sin(2 * np.pi * self.config.frequency * t)

        return ret


@singledispatch
def _create_input(conf: libsonata.SimulationConfig.InputBase) -> CurrentStimulator:
    msg = f"Unsupported input config: {type(conf)}"
    raise RuntimeError(msg)


STIMULATION_TYPES = {
    libsonata.SimulationConfig.Linear: Linear,
    libsonata.SimulationConfig.Pulse: Pulse,
    libsonata.SimulationConfig.Sinusoidal: Sinusoidal,
}

for type_, klass in STIMULATION_TYPES.items():
    _create_input.register(type_, klass)


def _convert_to_known_unit(v: str) -> brian2.Unit | int:
    if v == "1":  # unitless is `1` in brian2
        return int(v)
    if v not in KNOWN_UNITS:
        msg = f"Expecting a known brian2 unit, got: `{v}`"
        raise RuntimeError(msg)
    return getattr(brian2.units, v)


class NeuronParams(BaseModel):
    model: str = ""
    method: str = ""
    threshold: str = ""
    reset: str = ""
    refractory: str = ""

    @field_validator("model", mode="before")
    @classmethod
    def convert_list(cls, v: str | list) -> str:
        if isinstance(v, list):
            return "\n".join(v)
        return v


class FloatUnit(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    value: float
    unit: brian2.Unit | int

    def get(self) -> brian2.Quantity:
        return brian2.Quantity(self.value * self.unit)

    @model_validator(mode="before")
    @classmethod
    def convert(cls, v: tuple | list) -> dict:
        if not isinstance(v, (tuple, list)):
            msg = f"Unexpected FloatingUnit: `{v}`"
            raise TypeError(msg)
        return {"value": v[0], "unit": _convert_to_known_unit(v[1])}


class NeuronTemplate(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    params: NeuronParams
    namespace: dict[str, FloatUnit] = {}
    initial: dict[str, FloatUnit] = {}


class SynapseParams(BaseModel):
    model: str = ""
    on_pre: str = ""
    delay: FloatUnit | None = None


class SynapseTemplate(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    params: SynapseParams
    dynamics: dict[str, brian2.Unit | int]

    @field_validator("dynamics", mode="before")
    @classmethod
    def convert_list(cls, v: dict[str, str]) -> dict[str, brian2.Unit | int]:
        return {k: _convert_to_known_unit(v) for k, v in v.items()}


def _get_single_node_population(circuit: bluepysnap.Circuit) -> str:
    """Make sure there is only one node population, and retrieve its name."""
    assert len(circuit.nodes.population_names) == 1
    return next(iter(circuit.nodes.population_names))


def _make_poisson(
    simulation: bluepysnap.Simulation,
    config: libsonata.SimulationConfig.Poisson,
    n0: brian2.NeuronGroup,
) -> tuple[brian2.NeuronGroup, list]:
    L.info("Making Poisson Stimulus: rate: %f Hz, weight: %f mV", config.rate, config.weight)

    population_name = _get_single_node_population(simulation.circuit)
    node_ids = simulation.node_sets.to_libsonata.materialize(
        config.node_set, simulation.circuit.nodes[population_name].to_libsonata
    ).flatten()

    poisson_inputs = []
    for i in node_ids:
        p = brian2.PoissonInput(
            target=n0[i : i + 1],
            target_var="v",
            N=1,
            rate=config.rate * brian2.units.Hz,
            weight=config.weight * brian2.units.mV,
        )
        n0[i].rfc = 0 * brian2.units.ms  # no refractory period for Poisson targets
        poisson_inputs.append(p)

    return n0, poisson_inputs


def _get_close_spikes(ids: np.ndarray, times: np.ndarray, window: float) -> np.ndarray:
    """Return mask of spikes where the same cell has another spike within `window`.

    Only the 2nd spike will be marked as `close`
    """
    order = np.lexsort((times, ids))
    ids_sorted = ids[order]
    times_sorted = times[order]

    mask = np.zeros(len(ids), dtype=bool)
    mask[1:] = (ids_sorted[:-1] == ids_sorted[1:]) & (np.diff(times_sorted) <= window)

    result_mask = np.empty(len(ids), dtype=bool)
    result_mask[order] = mask
    return result_mask


def _get_spike_replay(
    simulation: bluepysnap.Simulation,
    input_: bluepysnap.input.SynapseReplay,
    n0: brian2.NeuronGroup,
    synapses: brian2.Synapses,
    synapse_template: SynapseTemplate,
) -> tuple[brian2.SpikeGeneratorGroup, brian2.Synapses]:
    assert len(input_.reader.get_population_names()) == 1
    population_name = next(iter(input_.reader.get_population_names()))

    node_ids = simulation.node_sets.to_libsonata.materialize(
        input_.node_set, simulation.circuit.nodes[population_name].to_libsonata
    ).flatten()

    spikes = input_.reader[population_name].get_dict()
    spikes, times = spikes["node_ids"], spikes["timestamps"]
    mask = np.isin(spikes, node_ids)
    spikes, times = spikes[mask], times[mask]

    spikes, times = spikes[times <= input_.duration], times[times <= input_.duration]

    mask = np.invert(_get_close_spikes(spikes, times, window=simulation.run.dt))

    L.debug(
        "Removing %d spikes of %d since they overlap within window dt=%f",
        len(mask) - np.sum(mask),
        len(mask),
        simulation.run.dt,
    )
    spikes, times = spikes[mask], times[mask]

    times = input_.delay + times

    L.info(
        "Replaying %d spikes from population `%s`, node_set: `%s`",
        len(times),
        population_name,
        input_.node_set,
    )

    replay = brian2.SpikeGeneratorGroup(len(n0), indices=spikes, times=times * brian2.units.ms)

    replay_connectivity = brian2.Synapses(
        replay,
        n0,
        model=synapse_template.params.model,
        on_pre=synapse_template.params.on_pre,
        delay=None
        if synapse_template.params.delay is None
        else synapse_template.params.delay.get(),
    )

    replay_connectivity.connect(i=synapses.i[:], j=synapses.j[:])

    edge_pop_name = next(iter(simulation.circuit.edges.population_names))
    edges = simulation.circuit.edges[edge_pop_name]
    edge_pop = edges.to_libsonata
    for name, unit in synapse_template.dynamics.items():
        values = edge_pop.get_attribute(name, edge_pop.select_all()) * unit
        setattr(replay_connectivity, name, values)

    return (replay, replay_connectivity)


class Inputs:
    def __init__(self, simulation: bluepysnap.Simulation) -> None:
        """Ibid."""
        self.simulation = simulation
        # `injectors` need the `I_inj` variable in the template, and require that
        # the equations of NeuronGroup includes changes
        self._injectors = [
            _create_input(input_)
            for input_ in self.simulation.inputs.values()
            if type(input_) in STIMULATION_TYPES
        ]

    def update_model_and_get_stims(self, model: str, neuron_count: int) -> tuple[str, dict, dict]:
        """Update model from template with requirements for Inputs.

        Strategy is to create "injectors" which are `brian2.TimedArray`'s with the values
        that are played to the particular neurons.  The neurons use an `indicator` which
        is a boolean mask where `True` is set if the particular neuron is set.

        Thus, the memory usage is O(Neurons_count + simulation_duration / dt) per input
        """
        if "I_inj" not in model:
            msg = f"Missing `I_inj` in equations: {model}; needed for current injection"
            raise RuntimeError(msg)

        model = re.sub(r".*I_inj\s*:\s*amp.*", "", model)

        population = self.simulation.circuit.nodes[
            _get_single_node_population(self.simulation.circuit)
        ].to_libsonata
        node_sets = self.simulation.node_sets.to_libsonata

        lines = []
        objs = {}
        indicators = {}
        seen_node_set = {}
        injection_sum = "\nI_inj = 0 * amp"
        for i, injection in enumerate(self._injectors):
            if injection.config.node_set in seen_node_set:
                objs[
                    f"stim{seen_node_set[injection.config.node_set]}"
                ].values += injection.get_currents(
                    self.simulation.dt, self.simulation.run.tstop
                ).values
                continue

            injection_sum += f" + I_inj{i}"
            lines.extend(
                (
                    f"I_inj{i} = stim{i}(t) * is_stimulated{i} : amp",
                    f"is_stimulated{i} : 1",
                )
            )
            idx = injection.get_selection(population=population, node_sets=node_sets).flatten()
            mask = np.zeros((neuron_count,), dtype=bool)
            mask[idx] = True
            indicators[f"is_stimulated{i}"] = mask
            objs[f"stim{i}"] = injection.get_currents(self.simulation.dt, self.simulation.run.tstop)
            seen_node_set[injection.config.node_set] = i

        model += "\n" + "\n".join(lines) + injection_sum + ": amp\n"

        return model, objs, indicators


def _get_inputs(
    simulation: bluepysnap.Simulation,
    n0: brian2.NeuronGroup,
    synapses: brian2.Synapses,
    synapse_template: SynapseTemplate,
) -> tuple[brian2.NeuronGroup, list[brian2.Group]]:
    inputs = []
    for input_ in simulation.inputs.values():
        if isinstance(input_, bluepysnap.input.SynapseReplay):
            inputs += _get_spike_replay(simulation, input_, n0, synapses, synapse_template)
        elif isinstance(input_, libsonata.SimulationConfig.Poisson):
            n0, poissons = _make_poisson(simulation, input_, n0)
            inputs += poissons

    return n0, inputs


def _get_reports(
    simulation: bluepysnap.Simulation, neurons: brian2.NeuronGroup
) -> tuple[brian2.StateMonitor | None, np.ndarray]:
    """Get voltage reports."""
    node_sets = simulation.node_sets.to_libsonata
    population = simulation.circuit.nodes[
        _get_single_node_population(simulation.circuit)
    ].to_libsonata

    selection = libsonata.Selection([])
    for name, report in simulation.reports.items():
        if isinstance(report, bluepysnap.frame_report.SomaReport):
            config = report.to_libsonata
            if config.sections != libsonata.SimulationConfig.Report.Sections.soma:
                msg = f"only sections == `soma` is supported, found: `{config.sections}`"
                raise RuntimeError(msg)
            if config.variable_name != "v":
                msg = "`variable_name`s other than `v` are not supported"
                raise RuntimeError(msg)
            if config.dt != simulation.run.dt:
                msg = "`dt` other than simulation.run.dt are not supported"
                raise RuntimeError(msg)
            if not config.enabled:
                L.warning("Skipping report: `%s` since not enabled", name)

            if node_set := config.cells or simulation.to_libsonata.node_set:
                selection |= node_sets.materialize(node_set, population)
            else:
                selection = population.select_all()
        else:
            msg = f"`{type(report)}` report type not handled, named {name}"
            raise TypeError(msg)

    if not selection:
        return None, np.array([])

    ids = np.sort(selection.flatten())
    id_mapping = np.zeros(ids[-1] + 1, dtype=np.min_scalar_type(ids[-1]))
    id_mapping[ids] = np.arange(len(ids))
    return brian2.StateMonitor(neurons, ["v"], record=ids), id_mapping


def _write_spikes(
    filepath: Path,
    population_name: str,
    timestamps: tuple[float, ...],
    node_ids: tuple[int, ...],
    sorting: str = "by_time",
    unit: str = "ms",
) -> Path:
    """Write spikes to an HDF5 file.

    Args:
        filepath: Path to the HDF5 file to be created or overwritten.
        population_name: Name of the node population.
        timestamps: Timestamps of the spikes.
        node_ids: Node IDs of the spikes.
        sorting: Sorting of the spikes. Can be "none", "by_id", or "by_time".
        unit: Unit of the timestamps.
    """
    L.info("Writing %d spikes to %s", len(timestamps), filepath)

    assert len(timestamps) == len(node_ids)
    string_dtype = h5py.special_dtype(vlen=str)
    sorting_dict = {"none": 0, "by_id": 1, "by_time": 2}
    sorting_type = h5py.enum_dtype(sorting_dict)
    sorting_value = sorting_dict[sorting]

    if node_ids and sorting == "by_time":
        timestamps, node_ids = zip(*sorted(zip(timestamps, node_ids, strict=True)), strict=True)
    elif node_ids and sorting == "by_id":
        node_ids, timestamps = zip(*sorted(zip(node_ids, timestamps, strict=True)), strict=True)

    with h5py.File(filepath, "w") as h5f:
        h5f.create_group("spikes")
        gpop_spikes = h5f.create_group(f"/spikes/{population_name}")
        gpop_spikes.attrs.create("sorting", data=sorting_value, dtype=sorting_type)
        dtimestamps = gpop_spikes.create_dataset("timestamps", data=timestamps, dtype=np.double)
        dtimestamps.attrs.create("units", data=unit, dtype=string_dtype)
        gpop_spikes.create_dataset("node_ids", data=node_ids, dtype=np.uint64)

    return filepath


def _create_neurons(simulation: bluepysnap.Simulation, inputs: Inputs) -> brian2.NeuronGroup:
    circuit = simulation.circuit
    assert len(circuit.nodes.population_names) == 1, "Only one population supported"
    nodes = circuit.nodes[next(iter(circuit.nodes.population_names))]
    L.info("Loading neuron population: `%s`, with %d ids", nodes.name, len(nodes.ids()))

    models_dir = Path(
        circuit.to_libsonata.node_population_properties(nodes.name).point_neuron_models_dir
    )

    templates = {}
    for tmpl in nodes.get(properties="model_template").unique():
        ext, name = tmpl.split(":")
        with (models_dir / f"{name}.{ext}").open() as fd:
            templates[tmpl] = NeuronTemplate.model_validate_json(fd.read())

    assert len(templates) == 1, "Only one template supported"
    template = next(iter(templates.values()))

    neuron_count = len(nodes.ids())
    model, stims, indicators = inputs.update_model_and_get_stims(
        template.params.model, neuron_count
    )

    n0 = brian2.NeuronGroup(
        N=neuron_count,
        name=nodes.name,
        model=model,
        method=template.params.method,
        threshold=template.params.threshold,
        reset=template.params.reset,
        refractory=template.params.refractory,
        namespace={**{k: v.get() for k, v in template.namespace.items()}, **stims},
    )

    # Override the initial membrane potential with `v_init` (mV) from the simulation config,
    # taking precedence over the value set by the neuron template.
    n0.v = simulation.conditions.v_init * brian2.units.mV

    for name, value in template.initial.items():
        setattr(n0, name, value.get())

    for name, value in indicators.items():
        setattr(n0, name, value)

    return n0


def _create_synapses(
    circuit: bluepysnap.Circuit, neurons: brian2.NeuronGroup
) -> tuple[brian2.Synapses, SynapseTemplate]:
    """Create synapses for circuit; all synapses are instantiated."""
    assert len(circuit.edges.population_names) == 1, "Only one population supported"
    edges = circuit.edges[next(iter(circuit.edges.population_names))]
    edge_pop = edges.to_libsonata
    L.info("Loading synapses: `%s` with %d synapses", edge_pop.name, edge_pop.size)

    models_dir = Path(
        circuit.to_libsonata.edge_population_properties(edge_pop.name).point_neuron_models_dir
    )
    src = edge_pop.source_nodes(edge_pop.select_all()).flatten()
    tgt = edge_pop.target_nodes(edge_pop.select_all()).flatten()

    if "model_template" in edge_pop.enumeration_names:
        template = edge_pop.enumeration_values("model_template")
        assert len(template) == 1
        template = next(iter(template))
    else:
        template = set(edge_pop.get_attribute("model_template", edge_pop.select_all()))
        template = next(iter(template))

    ext, name = template.split(":")
    with (models_dir / f"{name}.{ext}").open() as fd:
        synapse_template = SynapseTemplate.model_validate_json(fd.read())

    syn = brian2.Synapses(
        neurons,
        neurons,
        model=synapse_template.params.model,
        on_pre=synapse_template.params.on_pre,
    )
    syn.connect(i=np.array(src, np.int64), j=np.array(tgt, np.int64))

    syn.pre.delay = (
        0.0 * brian2.units.ms
        if synapse_template.params.delay is None
        else synapse_template.params.delay.get()
    )

    for name, unit in synapse_template.dynamics.items():
        values = edge_pop.get_attribute(name, edge_pop.select_all()) * unit
        setattr(syn, name, values)

    return syn, synapse_template


class ConnectionOverride:
    def __init__(
        self, config: libsonata.SimulationConfig.ConnectionOverride, sim_config_path: Path
    ) -> None:
        """Ibid."""
        if config.spont_minis is not None:
            msg = "connection_overrides::spont_minis is not supported"
            raise RuntimeError(msg)
        if config.synapse_configure is not None:
            msg = "connection_overrides::synapse_configure is not supported"
            raise RuntimeError(msg)
        if config.modoverride is not None:
            msg = "connection_overrides::modoverride is not supported"
            raise RuntimeError(msg)
        if config.neuromodulation_dtc is not None:
            msg = "connection_overrides::neuromodulation_dtc is not supported"
            raise RuntimeError(msg)
        if config.neuromodulation_strength is not None:
            msg = "connection_overrides::neuromodulation_strength is not supported"
            raise RuntimeError(msg)

        self.config = config
        self.sim_config_path = sim_config_path

    @property
    def at(self) -> float:
        """Time at which the override should start, in ms."""
        return self.config.delay

    def __call__(self, net: Brian2Network) -> None:
        simulation = bluepysnap.Simulation(self.sim_config_path)
        circuit = simulation.circuit
        node_sets = simulation.node_sets.to_libsonata

        nodes = circuit.nodes[next(iter(circuit.nodes.population_names))].to_libsonata

        src_ids = node_sets.materialize(self.config.source, nodes)
        tgt_ids = node_sets.materialize(self.config.target, nodes)

        edges = circuit.edges[next(iter(circuit.edges.population_names))]
        edge_pop = edges.to_libsonata
        # All synapses have been instantiated, so we can index using the `connecting_edges`
        selection = edge_pop.connecting_edges(src_ids.flatten(), tgt_ids.flatten())

        if self.config.weight is not None:
            net.synapses.w[selection.flatten()] = self.config.weight * brian2.units.mV

        if self.config.synapse_delay_override is not None:
            net.synapses.delay[selection.flatten()] = (
                self.config.synapse_delay_override * brian2.units.ms
            )


def _gather_connection_overrides(simulation: bluepysnap.Simulation) -> list[Event]:
    """Get `connection_overrides` SONATA configuration blocks and make Events."""
    ret = []

    for connection_override in simulation.to_libsonata.connection_overrides():
        co = ConnectionOverride(connection_override, Path(simulation._simulation_config_path))  # noqa: SLF001
        ret.append(Event(at=co.at, func=co))

    return ret


def _build_brian2_network(simulation: bluepysnap.Simulation) -> Brian2Network:
    brian2.defaultclock.dt = simulation.run.dt * brian2.units.ms
    brian2.seed(simulation.run.random_seed)

    current_inputs = Inputs(simulation)
    events = _gather_connection_overrides(simulation)

    neurons = _create_neurons(simulation, current_inputs)

    synapses, synapse_template = _create_synapses(simulation.circuit, neurons)

    spike_monitor = brian2.SpikeMonitor(neurons)

    state_monitor, report_id_mapping = _get_reports(simulation, neurons)

    neurons, inputs = _get_inputs(simulation, neurons, synapses, synapse_template)

    net = Brian2Network(
        neurons=neurons,
        synapses=synapses,
        spike_monitor=spike_monitor,
        inputs=inputs,
        state_monitor=state_monitor,
        report_id_mapping=report_id_mapping,
        events=events,
    )

    return net


def _write_soma_report(
    output_path: Path,
    name: str,
    node_ids: np.ndarray,
    values: np.ndarray,
    unit: brian2.units.Unit,
    start: float,
    end: float,
    dt: float,
) -> None:
    """Ibid."""
    values = values[:, math.floor(start / dt) : min(math.ceil(end / dt) + 1, values.shape[1])]
    string_dtype = h5py.special_dtype(vlen=str)
    with h5py.File(output_path, "w") as h5f:
        g = h5f.create_group(f"/report/{name}")
        g.create_dataset("data", data=values.T / unit, dtype=np.float32).attrs.create(
            "units", data=str(unit), dtype=string_dtype
        )
        mapping = h5f.create_group(f"/report/{name}/mapping")
        mapping.create_dataset("node_ids", data=node_ids, dtype=np.uint64)
        mapping.create_dataset(
            "index_pointers", data=np.arange(values.shape[0] + 1), dtype=np.uint64
        )
        mapping.create_dataset("element_ids", data=np.zeros(values.shape[0]), dtype=np.uint32)
        mapping.create_dataset("time", data=(start, end, dt), dtype=np.double).attrs.create(
            "units", data="ms", dtype=string_dtype
        )


def _write_reports(
    simulation: bluepysnap.Simulation,
    spike_monitor: brian2.SpikeMonitor,
    state_monitor: brian2.StateMonitor | None,
    report_id_mapping: np.ndarray,
) -> None:
    """Ibid."""
    output_dir = Path(simulation.output.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    spikes = [
        (k, v / brian2.units.ms) for k, vs in spike_monitor.spike_trains().items() for v in vs
    ]

    node_ids, timestamps = zip(*spikes, strict=True) if spikes else ((), ())
    L.info("%d neurons spiked %d times", len(spike_monitor.spike_trains()), len(node_ids))
    Path(simulation.output.spikes_file).parent.mkdir(exist_ok=True, parents=True)
    _write_spikes(
        filepath=simulation.output.spikes_file,
        population_name=_get_single_node_population(simulation.circuit),
        timestamps=timestamps,
        node_ids=node_ids,
    )

    if state_monitor is None:
        return

    node_sets = simulation.node_sets.to_libsonata
    population_name = _get_single_node_population(simulation.circuit)
    population = simulation.circuit.nodes[population_name].to_libsonata

    for report in simulation.reports.values():
        if not isinstance(report, bluepysnap.frame_report.SomaReport):
            continue

        config = report.to_libsonata
        if not config.enabled:
            continue

        if node_set := config.cells or simulation.to_libsonata.node_set:
            selection = node_sets.materialize(node_set, population)
        else:
            selection = population.select_all()

        ids = np.sort(selection.flatten())

        Path(config.file_name).parent.mkdir(exist_ok=True, parents=True)

        _write_soma_report(
            config.file_name,
            population_name,
            ids,
            state_monitor.v[report_id_mapping[ids], :],
            unit=brian2.units.mV,
            start=config.start_time,
            end=min(config.end_time, simulation.run.tstop),
            dt=simulation.run.dt,
        )


def run_sonata_brian2_trial(simulation_config_path: Path) -> Brian2Network:
    """Returns the path to the spikes file."""
    simulation = bluepysnap.Simulation(simulation_config_path)

    brian2.start_scope()
    net = _build_brian2_network(simulation)

    network = brian2.Network(
        net.neurons,
        net.synapses,
        net.spike_monitor,
        *net.inputs,
        *([] if net.state_monitor is None else [net.state_monitor]),
    )

    L.info(
        "Running simulation with `%s` backend",
        brian2.prefs.codegen.target,
    )

    L.info("Running simulation")

    queue = list(net.events)
    heapq.heapify(queue)

    current_t = 0.0
    while current_t < simulation.run.tstop:
        next_t = min(queue[0].at, simulation.run.tstop) if queue else simulation.run.tstop
        network.run((next_t - current_t) * brian2.units.ms)
        current_t = next_t

        while queue and queue[0].at <= current_t:
            event = heapq.heappop(queue)
            event.func(net)

    _write_reports(simulation, net.spike_monitor, net.state_monitor, net.report_id_mapping)

    return net


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option("--simulation-path", type=REQUIRED_PATH)
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v for INFO, -vv for DEBUG)")
def sonata_simulation(
    simulation_path: str,
    verbose: int,
) -> None:

    log_level = [logging.WARNING, logging.INFO, logging.DEBUG][min(verbose, 2)]
    logging.basicConfig(level=log_level, force=True)
    if verbose:
        brian2.BrianLogger.log_level_debug()

    run_sonata_brian2_trial(Path(simulation_path))


def _init_entitysdk_client(
    virtual_lab_id: uuid.UUID,
    project_id: uuid.UUID,
    environment: str,
    persistent_token_id: str,
) -> Client:
    project_context = ProjectContext(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
    )
    token_manager = TokenFromFunction(
        partial(
            get_token,
            environment=DeploymentEnvironment(environment),
            auth_mode=AuthMode.persistent_token,
            persistent_token_id=persistent_token_id,
        ),
    )
    local_store = None
    if "LOCAL_STORE_PREFIX" in os.environ:
        local_store = LocalAssetStore(prefix=Path(os.environ["LOCAL_STORE_PREFIX"]))

    return Client(
        project_context=project_context,
        environment=environment,
        token_manager=token_manager,
        local_store=local_store,
    )


@contextlib.contextmanager
def activity_wrapper(
    entitysdk_client: Client,
    activity_id: uuid.UUID,
    activity_type: type[Activity],
) -> Iterator[None]:
    """Ensure that the activity status is updated correctly in entitycore."""

    def _update_activity_status(attrs: dict) -> None:
        """Update activity status."""
        entitysdk_client.update_entity(
            entity_id=activity_id,
            entity_type=activity_type,
            attrs_or_entity=attrs,
        )

    _update_activity_status({"status": ActivityStatus.running})
    try:
        yield
    except Exception:
        _update_activity_status(
            {"status": ActivityStatus.error, "end_time": datetime.now(tz=timezone.utc)}  # noqa: UP017
        )
        raise  # re-raise the exception so that it can be handled by the job wrapper
    else:
        _update_activity_status(
            {"status": ActivityStatus.done, "end_time": datetime.now(tz=timezone.utc)}  # noqa: UP017
        )


def sonata_main(
    *,
    client: Client,
    simulation_id: uuid.UUID,
    simulation_execution_id: uuid.UUID,
    workdir: Path,
) -> None:
    L.info("Loading simulation %s", simulation_id)
    model = client.get_entity(entity_id=simulation_id, entity_type=models.Simulation)
    simulation_config_file = stage_simulation(
        client=client,
        model=model,
        output_dir=workdir,
        circuit_config_path=None,
        override_results_dir=workdir,
    )

    with activity_wrapper(
        entitysdk_client=client,
        activity_id=simulation_execution_id,
        activity_type=models.SimulationExecution,
    ):
        run_sonata_brian2_trial(simulation_config_file)

    L.info("Registering simulation result")
    simulation_result = client.register_entity(
        models.SimulationResult(
            name="Simulation result",
            description="",
            simulation_id=simulation_id,
        )
    )
    L.info("Uploading assets for simulation")
    assert simulation_result.id

    simulation_config = libsonata.SimulationConfig.from_file(simulation_config_file)

    client.upload_file(
        entity_id=simulation_result.id,
        entity_type=models.SimulationResult,
        file_path=Path(simulation_config.output.output_dir) / simulation_config.output.spikes_file,
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.spike_report,
    )

    for name in simulation_config.list_report_names:
        report = simulation_config.report(name)
        client.upload_file(
            entity_id=simulation_result.id,
            entity_type=models.SimulationResult,
            file_path=Path(report.file_name),
            file_content_type=ContentType.application_x_hdf5,
            asset_label=AssetLabel.voltage_report,
        )

    L.info("Updating simulation execution")
    client.update_entity(
        entity_id=simulation_execution_id,
        entity_type=models.SimulationExecution,
        attrs_or_entity={
            "used_ids": [simulation_id],
            "generated_ids": [simulation_result.id],
            "end_time": datetime.now(UTC),
            "status": ActivityStatus.done,
        },
    )

    L.info("Process completed!")


@cli.command()
@click.option("--virtual-lab-id", type=click.UUID)
@click.option("--project-id", type=click.UUID)
@click.option("--simulation-id", type=click.UUID)
@click.option("--simulation-execution-id", type=click.UUID)
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v for INFO, -vv for DEBUG)")
def sonata_simulation_task(
    virtual_lab_id: uuid.UUID,
    project_id: uuid.UUID,
    simulation_id: uuid.UUID,
    simulation_execution_id: uuid.UUID,
    verbose: int,
) -> None:

    log_level = [logging.WARNING, logging.INFO, logging.DEBUG][min(verbose, 2)]
    logging.basicConfig(level=log_level, force=True)
    L.setLevel(log_level)
    if verbose:
        brian2.BrianLogger.log_level_debug()

    client = _init_entitysdk_client(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        environment=os.environ["DEPLOYMENT"],
        persistent_token_id=os.environ["PERSISTENT_TOKEN_ID"],
    )

    with tempfile.TemporaryDirectory(delete=False) as tmpdir:
        sonata_main(
            client=client,
            simulation_id=simulation_id,
            simulation_execution_id=simulation_execution_id,
            workdir=Path(tmpdir),
        )


if __name__ == "__main__":
    cli()

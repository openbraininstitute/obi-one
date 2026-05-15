import logging
import uuid
from pathlib import Path

import bluepysnap
import brian2
import brian2.units
import click
import h5py
import libsonata
import numpy as np
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

POPULATION = "drosophila"

REQUIRED_PATH = click.Path(exists=True, readable=True, dir_okay=False, resolve_path=True)
L = logging.getLogger(__name__)
KNOWN_UNITS = {u for u in dir(brian2.units) if not u.startswith("_")}


def _convert_to_known_unit(v: str):
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
    unit: brian2.Unit

    def get(self) -> brian2.Quantity:
        return brian2.Quantity(self.value * self.unit)

    @model_validator(mode="before")
    @classmethod
    def convert(cls, v) -> dict:
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
    dynamics: dict[str, brian2.Unit]

    @field_validator("dynamics", mode="before")
    @classmethod
    def convert_list(cls, v: dict[str, str]) -> dict[str, brian2.Unit]:
        return {k: _convert_to_known_unit(v) for k, v in v.items()}


def _make_poisson(
    simulation: bluepysnap.Simulation,
    config: libsonata.SimulationConfig.Poisson,
    n0: brian2.NeuronGroup,
):
    L.info("Making Poisson Stimulus: rate: %f Hz, weight: %f mV", config.rate, config.weight)
    exc_node_ids = simulation.circuit.node_sets.to_libsonata.materialize(
        "sugar", simulation.circuit.nodes["drosophila"].to_libsonata
    ).flatten()

    poisson_inputs = []
    for i in exc_node_ids:
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


def _make_spikes(spike_input):
    L.info("Making SpikeReplay input")
    sr = libsonata.SpikeReader(spike_input.spike_file)
    sp = sr[POPULATION]
    ids, times = zip(*sp.get())
    return


def _get_inputs(
    simulation: bluepysnap.Simulation, n0: brian2.NeuronGroup
) -> tuple[brian2.NeuronGroup, list]:

    inputs = []
    for input_ in simulation.inputs.values():
        if isinstance(input_, bluepysnap.input.SynapseReplay):
            pass
            # inputs.append(_make_spikes(input_))
        elif isinstance(input_, libsonata.SimulationConfig.Poisson):
            n0, poissons = _make_poisson(simulation, input_, n0)
            inputs += poissons

    return n0, inputs


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
    if sorting == "by_time":
        timestamps, node_ids = zip(*sorted(zip(timestamps, node_ids, strict=True)), strict=True)
    elif sorting == "by_id":
        node_ids, timestamps = zip(*sorted(zip(node_ids, timestamps, strict=True)), strict=True)
    with h5py.File(filepath, "w") as h5f:
        h5f.create_group("spikes")
        gpop_spikes = h5f.create_group(f"/spikes/{population_name}")
        gpop_spikes.attrs.create("sorting", data=sorting_value, dtype=sorting_type)
        dtimestamps = gpop_spikes.create_dataset("timestamps", data=timestamps, dtype=np.double)
        dtimestamps.attrs.create("units", data=unit, dtype=string_dtype)
        gpop_spikes.create_dataset("node_ids", data=node_ids, dtype=np.uint64)

    return filepath


def _create_neurons(circuit: bluepysnap.Circuit) -> brian2.NeuronGroup:
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

    n0 = brian2.NeuronGroup(
        N=len(nodes.ids()),
        name=nodes.name,
        model=template.params.model,
        method=template.params.method,
        threshold=template.params.threshold,
        reset=template.params.reset,
        refractory=template.params.refractory,
        namespace={k: v.get() for k, v in template.namespace.items()},
    )

    for name, value in template.initial.items():
        setattr(n0, name, value.get())

    return n0


def _create_synapses(circuit: bluepysnap.Circuit, neurons: brian2.NeuronGroup) -> brian2.Synapses:
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
        ext, name = template.split(":")
        with (models_dir / f"{name}.{ext}").open() as fd:
            synapse = SynapseTemplate.model_validate_json(fd.read())

    syn = brian2.Synapses(
        neurons,
        neurons,
        model=synapse.params.model,
        on_pre=synapse.params.on_pre,
        delay=None if synapse.params.delay is None else synapse.params.delay.get(),
    )
    syn.connect(i=np.array(src, np.int64), j=np.array(tgt, np.int64))

    for name, unit in synapse.dynamics.items():
        values = edge_pop.get_attribute(name, edge_pop.select_all()) * unit
        setattr(syn, name, values)

    return syn


def run_sonata_brian2_trial(simulation_config_path: Path) -> Path:
    simulation = bluepysnap.Simulation(simulation_config_path)
    circuit = simulation.circuit

    assert circuit.nodes.population_names == ["drosophila"]

    brian2.seed(simulation.run.random_seed)
    brian2.start_scope()

    neurons = _create_neurons(circuit)
    synapses = _create_synapses(circuit, neurons)

    spike_monitor = brian2.SpikeMonitor(neurons)

    neurons, inputs = _get_inputs(simulation, neurons)

    net = brian2.Network(neurons, synapses, spike_monitor, *inputs)
    L.info("Running simulation")
    net.run(duration=simulation.run.tstop * brian2.units.ms)

    output_dir = Path(simulation.output.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    node_ids, timestamps = zip(
        *[(k, float(v)) for k, vs in spike_monitor.spike_trains().items() for v in vs], strict=True
    )
    L.info("%d neurons spiked %d times", len(spike_monitor.spike_trains()), len(node_ids))
    spikes_path = _write_spikes(
        filepath=output_dir / simulation.output.spikes_file,
        population_name=POPULATION,
        timestamps=timestamps,
        node_ids=node_ids,
    )
    return spikes_path


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

    run_sonata_brian2_trial(Path(simulation_path))


import contextlib
from enum import auto
from entitysdk.staging import stage_circuit, stage_simulation
import os
from entitysdk.models.activity import Activity
from entitysdk import Client, models, ProjectContext
from entitysdk.token_manager import TokenFromFunction
from functools import partial
from obi_auth import get_token
from collections.abc import Iterator
from entitysdk.types import AssetLabel, ContentType, StrEnum, ActivityStatus
from datetime import UTC, datetime, timezone
import tempfile
from entitysdk.utils.store import LocalAssetStore


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
            environment=environment,
            auth_mode="persistent_token",
            persistent_token_id=persistent_token_id,
        ),
    )
    local_store = None
    if "LOCAL_STORE_PREFIX" in os.environ:
        local_store = LocalAssetStore(prefix=os.environ["LOCAL_STORE_PREFIX"])

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
        spikes_report_filepath = run_sonata_brian2_trial(simulation_config_file)

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
    client.upload_file(
        entity_id=simulation_result.id,
        entity_type=models.SimulationResult,
        file_path=spikes_report_filepath,
        file_content_type=ContentType.application_x_hdf5,
        asset_label=AssetLabel.spike_report,
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
    L.setLevel(log_level)  # set only the log level in the script

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

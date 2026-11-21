#!/usr/bin/env python3
"""A Brian2 point-neuron circuit and the NeuroMechFly body, wired as a fly's are, in closed loop.

The circuit says which of its neurons the body drives and reads, and how: its body interface
(``interface.py``). The odour reaches it only through its olfactory receptor neurons, each firing
for the odour at its own antenna or palp; the legs move only as its motor neurons drive their
muscles; and its proprioceptors and leg bristles feel the joints and the floor. The network and the
body run together from the start, exchanging every ``coupling_step`` (1 ms): there is no stepping
controller and no steering rule. The simulation config's ``neuromechfly`` section is the
experiment (``config.ClosedLoopConfig``): the arena, pushes and legs taken over.

The spikes are written as in any Brian2 simulation; the body's trajectory and a summary of the
episode are added to the spikes file under ``/neuromechfly``. A replay of everything the body did,
for the 3D viewer, goes in it as ``/neuromechfly_replay`` (JSON), so the registered spike report
carries it; all three are also written beside the spikes file.
"""

import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import bluepysnap
import brian2
import brian2.units
import click
import h5py
import libsonata
import numpy as np
import pandas as pd
from entitysdk import Client, models
from entitysdk.staging import stage_simulation
from entitysdk.types import ActivityStatus

from obi_one.db_sdk.registration.simulation_result import register_simulation_results
from obi_one.scientific.library.simulation.brian2.simulate_brian2 import (
    PROGRESS_REPORT_PERIOD_SECONDS,
    REQUIRED_PATH,
    SimulationProgress,
    activity_wrapper,
    advance_network,
    build_brian2_network,
    event_queue,
    get_single_node_population,
    init_entitysdk_client,
    network_of,
    write_reports,
)
from obi_one.scientific.library.simulation.neuromechfly.body import Body
from obi_one.scientific.library.simulation.neuromechfly.config import SECTION, ClosedLoopConfig
from obi_one.scientific.library.simulation.neuromechfly.interface import read_body_interface
from obi_one.scientific.library.simulation.neuromechfly.wiring import Muscles, Senses

L = logging.getLogger(__name__)

# A step of more than this many mm/s counts as moving.
MOVING_SPEED_MM_PER_S = 1.0
# Body time from one replay frame, and one trajectory row, to the next (ms). The viewer blends
# between frames, so slow replays stay smooth.
REPLAY_FRAME_MS = 10.0


def circuit_config_path(simulation_config_path: Path) -> Path:
    """The simulation's circuit config (its ``network``), which may be relative to it."""
    config = json.loads(Path(simulation_config_path).read_text(encoding="utf-8"))
    network = Path(config["network"])
    return network if network.is_absolute() else Path(simulation_config_path).parent / network


def read_closed_loop_config(simulation_config_path: Path) -> ClosedLoopConfig:
    """Return the ``neuromechfly`` section of a SONATA simulation config."""
    config = json.loads(Path(simulation_config_path).read_text(encoding="utf-8"))
    if SECTION not in config:
        msg = f"{simulation_config_path} has no '{SECTION}' section."
        raise ValueError(msg)
    return ClosedLoopConfig.model_validate(config[SECTION])


def episode_summary(trajectory: pd.DataFrame, body: Body, loop: ClosedLoopConfig) -> dict:
    """What the body did in the episode."""
    path = trajectory[["x", "y"]].to_numpy()
    steps = np.linalg.norm(np.diff(path, axis=0), axis=1)
    speed = steps / (np.diff(trajectory["body_time"].to_numpy()) if len(path) > 1 else 1)
    path_length = float(steps.sum())
    displacement = float(np.linalg.norm(path[-1] - path[0])) if len(path) else 0.0
    overturned = trajectory.loc[~trajectory["upright"], "body_time"]
    return {
        "sources_total": len(loop.arena.odour_sources),
        "sources_reached": len(body.reached),
        "reach_times_s": [time / 1000 for _, time in body.reached],
        "episode_s": body.time_ms / 1000,
        "physics_fault": body.physics_fault,
        "overturned_s": float(overturned.iloc[0]) if len(overturned) else None,
        "path_length_mm": path_length,
        "straightness": displacement / path_length if path_length > 0 else 0.0,
        "median_speed_mm_per_s": float(np.median(speed)) if len(steps) else 0.0,
        "fraction_moving": float(np.mean(speed > MOVING_SPEED_MM_PER_S)) if len(steps) else 0.0,
    }


def replay_document(body: Body, loop: ClosedLoopConfig, start_ms: float, summary: dict) -> dict:
    """What the 3D viewer replays the episode from: the body's frames (``Body.frame``), the arena
    and the experiment. Frame ``i`` is at body time ``i * frame_ms``, and body time 0 at spike time
    ``start_ms``.
    """
    frames = body.frames
    return {
        "version": 1,
        "units": "mm, μN, radians, quaternions (w, x, y, z), ms",
        "frame_ms": body.record_every * loop.body_timestep,
        "start_ms": start_ms,
        "arena": loop.arena.model_dump(mode="json"),
        "forces": [force.model_dump(mode="json") for force in loop.forces],
        "leg_overrides": [override.model_dump(mode="json") for override in loop.leg_overrides],
        "sources_reached": [{"source": source, "time_ms": time} for source, time in body.reached],
        "summary": summary,
        "frames": {
            "thorax": np.round([frame["thorax"] for frame in frames], 5).tolist(),
            "joints": np.round([frame["joints"] for frame in frames], 4).tolist(),
            "forces": [
                [
                    None if force is None else np.round(force, 4).tolist()
                    for force in frame["forces"]
                ]
                for frame in frames
            ],
            "overrides": [frame["overrides"] for frame in frames],
            "upright": [frame["upright"] for frame in frames],
        },
    }


def write_body_outputs(
    spikes_file: Path, trajectory: pd.DataFrame, summary: dict, replay: dict
) -> None:
    """Add the trajectory, summary and replay to the spikes file; write them beside it too."""
    with h5py.File(spikes_file, "a") as h5:
        group = h5.create_group(SECTION)
        for column in trajectory.columns:
            group.create_dataset(column, data=trajectory[column].to_numpy())
        group.attrs["summary"] = json.dumps(summary)
        # A simulation result's assets can only be h5 reports, so the replay rides in this one.
        h5.create_dataset(f"{SECTION}_replay", data=json.dumps(replay))
    trajectory.to_csv(spikes_file.parent / f"{SECTION}_trajectory.csv", index=False)
    (spikes_file.parent / f"{SECTION}_summary.json").write_text(json.dumps(summary, indent=2))
    (spikes_file.parent / f"{SECTION}_replay.json").write_text(json.dumps(replay))


def run_closed_loop(  # ruff: ignore[too-many-locals, too-many-statements]
    simulation_config_path: Path, *, profile: bool = False
) -> dict:
    """Run the closed loop configured in ``simulation_config_path``; return the summary."""
    simulation = bluepysnap.Simulation(simulation_config_path)
    loop = read_closed_loop_config(simulation_config_path)
    interface = read_body_interface(simulation.circuit, circuit_config_path(simulation_config_path))
    ms, hz = brian2.units.ms, brian2.units.Hz

    brian2.start_scope()
    net = build_brian2_network(simulation)
    population = simulation.circuit.nodes[get_single_node_population(simulation.circuit)]
    senses = Senses(population, interface)
    muscles = Muscles(population, interface)
    if not len(senses.ids) or not len(muscles.names):
        msg = "The circuit's body interface needs sensory neurons and motor neurons."
        raise ValueError(msg)
    L.info(
        "Body interface: %d sensory neurons, %d motor neurons driving %d muscles",
        len(senses.ids),
        len(muscles.neuron_ids),
        len(muscles.names),
    )

    # Each Poisson event fires its sensory neuron, so the neuron fires at the rate its sense sets.
    net.neurons.rfc[senses.ids] = 0 * ms
    drive = brian2.PoissonGroup(
        len(senses.ids), rates=senses.spontaneous * hz, name="neuromechfly_senses"
    )
    kick = brian2.Synapses(
        drive,
        net.neurons,
        on_pre=f"v_post += {interface.sensing.receptor_kick}*mV",
        name="neuromechfly_sense_kick",
    )
    kick.connect(i=np.arange(len(senses.ids)), j=senses.ids)
    activation = brian2.NeuronGroup(
        len(muscles.names),
        "da/dt = -a / tau : 1",
        method="exact",
        namespace={"tau": muscles.time_constant_ms * ms},
        name="neuromechfly_muscles",
    )
    motor = brian2.Synapses(
        net.neurons, activation, model="w : 1", on_pre="a_post += w", name="neuromechfly_motor"
    )
    motor.connect(i=muscles.neuron_ids, j=muscles.unit_of_neuron)
    motor.w = muscles.increments

    body = Body(
        loop.arena,
        timestep_ms=loop.body_timestep,
        seed=simulation.run.random_seed,
        motor=interface.motor,
        forces=loop.forces,
        leg_overrides=loop.leg_overrides,
        frame_ms=REPLAY_FRAME_MS,
    )
    physics_steps = round(loop.coupling_step / loop.body_timestep)
    record_every = max(1, round(REPLAY_FRAME_MS / loop.coupling_step))
    exchanges = 0
    perturbed = False

    def row() -> dict:
        """Where the body is now, for the trajectory."""
        x, y, z = body.position
        return {
            "time": body.time_ms,
            "body_time": body.time_ms / 1000,
            "x": x,
            "y": y,
            "z": z,
            "heading": body.heading,
            "sources_reached": len(body.reached),
            "perturbed": perturbed,
            "upright": body.upright,
        }

    rows = [row()]

    @brian2.network_operation(dt=loop.coupling_step * ms, when="start", name="neuromechfly_body")
    def exchange() -> None:
        """Move the body by its muscles for a coupling step, then let its senses fire."""
        nonlocal exchanges, perturbed
        if body.physics_fault:
            drive.rates = senses.spontaneous * hz
            return
        torques, grip = muscles.drive(np.asarray(activation.a[:]))
        perturbed |= body.advance(torques, grip, physics_steps)
        body.note_sources()
        drive.rates = senses.rates(body.state(loop.coupling_step)) * hz
        exchanges += 1
        if exchanges % record_every == 0 or body.physics_fault:
            rows.append(row())
            perturbed = False
        if body.physics_fault:
            L.warning("Physics fault at %.3f s: the body stops there", body.time_ms / 1000)

    network = network_of(net)
    network.add(drive, kick, activation, motor, exchange)
    queue = event_queue(net)
    progress = SimulationProgress(simulation.run.tstop, period=PROGRESS_REPORT_PERIOD_SECONDS)
    advance_network(
        network, net, queue, 0.0, simulation.run.tstop, progress=progress, profile=profile
    )

    write_reports(simulation, net.spike_monitor, net.state_monitor, net.report_id_mapping)
    trajectory = pd.DataFrame(rows)
    summary = episode_summary(trajectory, body, loop)
    replay = replay_document(body, loop, 0.0, summary)
    write_body_outputs(Path(simulation.output.spikes_file), trajectory, summary, replay)
    L.info("Episode: %s", summary)
    if profile:
        print(brian2.profiling_summary(net=network))  # ruff: ignore[print]
    return summary


def closed_loop_main(
    *,
    client: Client,
    simulation_id: uuid.UUID,
    simulation_execution_id: uuid.UUID,
    workdir: Path,
    profile: bool,
) -> None:
    """Stage the simulation, run the closed loop and register its result."""
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
        run_closed_loop(simulation_config_file, profile=profile)

    simulation_config = libsonata.SimulationConfig.from_file(simulation_config_file)
    simulation_result = register_simulation_results(
        client=client,
        simulation_id=simulation_id,
        spike_report_file=Path(simulation_config.output.spikes_file),
        voltage_report_files=[
            Path(simulation_config.report(name).file_name)
            for name in simulation_config.list_report_names
        ],
        name="Simulation result",
        description="Closed-loop simulation result: spikes, with the body's trajectory under "
        f"/{SECTION}",
    )
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


def configure_logging(verbose: int) -> None:
    """INFO for this module on stdout, beside the progress lines; ``verbose`` for the rest."""
    log_level = [logging.WARNING, logging.INFO, logging.DEBUG][min(verbose, 2)]
    logging.basicConfig(level=log_level, force=True)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    L.addHandler(handler)
    L.propagate = False
    L.setLevel(min(log_level, logging.INFO))
    if verbose > 1:
        brian2.BrianLogger.log_level_debug()


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option("--simulation-path", type=REQUIRED_PATH)
@click.option("--profile", is_flag=True, help="Turn on internal brian2 profiling")
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v for INFO, -vv for DEBUG)")
def sonata_simulation(simulation_path: str, verbose: int, *, profile: bool) -> None:
    configure_logging(verbose)
    summary = run_closed_loop(Path(simulation_path), profile=profile)
    click.echo(json.dumps(summary, indent=2))


@cli.command()
@click.option("--virtual-lab-id", type=click.UUID)
@click.option("--project-id", type=click.UUID)
@click.option("--simulation-id", type=click.UUID)
@click.option("--simulation-execution-id", type=click.UUID)
@click.option("--profile", is_flag=True, help="Turn on internal brian2 profiling")
@click.option("-v", "--verbose", count=True, help="Increase verbosity (-v for INFO, -vv for DEBUG)")
def sonata_simulation_task(
    virtual_lab_id: uuid.UUID,
    project_id: uuid.UUID,
    simulation_id: uuid.UUID,
    simulation_execution_id: uuid.UUID,
    *,
    profile: bool,
    verbose: int,
) -> None:
    configure_logging(verbose)
    client = init_entitysdk_client(
        virtual_lab_id=virtual_lab_id,
        project_id=project_id,
        environment=os.environ["DEPLOYMENT"],
        persistent_token_id=os.environ["PERSISTENT_TOKEN_ID"],
    )
    with tempfile.TemporaryDirectory(delete=False) as tmpdir:
        closed_loop_main(
            client=client,
            simulation_id=simulation_id,
            simulation_execution_id=simulation_execution_id,
            workdir=Path(tmpdir),
            profile=profile,
        )


if __name__ == "__main__":
    cli()

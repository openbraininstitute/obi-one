"""Simulation execution module for OBI-One.

This module provides functionality to run simulations using different backends
(BlueCelluLab, Neurodamus) based on the simulation requirements.
"""

import argparse
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bluecellulab import CircuitSimulation
from bluecellulab.reports.manager import ReportManager
from bluecellulab.reports.utils import (
    collect_local_payload,
    collect_local_spikes,
    gather_payload_to_rank0,
    gather_recording_sites,
    payload_to_cells,
    prepare_recordings_for_reports,
)
from neuron import h

from obi_one.types import SimulationBackend
from obi_one.utils.io import load_json

logger = logging.getLogger(__name__)


@dataclass
class MPIProcess:
    parallel_context: Any

    @property
    def rank(self) -> int:
        """Return the current rank id of the MPI process."""
        return int(self.parallel_context.id())

    @property
    def size(self) -> int:
        """Return the total number of MPI processes."""
        return int(self.parallel_context.nhost())


@contextmanager
def neuron_mpi_process(libnrnmech_path: str) -> Iterator[MPIProcess]:
    h.nrn_load_dll(libnrnmech_path)
    h.nrnmpi_init()
    parallel_context = h.ParallelContext()
    process = MPIProcess(parallel_context)

    _setup_mpi_logging(rank=process.rank)

    try:
        yield process
    except Exception:
        logger.exception("Rank %d failed", process.rank)
        h.quit()
        return

    logger.info("Rank %d: Cleaning up...", process.rank)
    parallel_context.barrier()
    h.quit()


def _setup_mpi_logging(rank: int) -> None:
    """Configure stdout logging for MPI processes."""
    logger = logging.getLogger()

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(f"[Rank {rank}] %(asctime)s %(levelname)s %(name)s: %(message)s")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Avoid duplicate handlers if imported multiple times
    logger.handlers.clear()
    logger.addHandler(handler)


def get_instantiate_gids_params(simulation_config_data: dict[str, Any]) -> dict[str, Any]:
    """Determine instantiate_gids parameters from simulation config.

    This function gives parameters for sim.instantiate_gids() based on the
    simulation config. See the package BlueCellulab/bluecellulab/circuit_simulation.py
    for more details.

    Args:
        simulation_config_data: Loaded simulation configuration
    Returns:
        Dictionary of parameters for instantiate_gids.
    """
    params = {
        "add_stimuli": False,
        "add_synapses": False,
        "add_minis": False,
        "add_replay": False,
        "add_projections": False,
        "interconnect_cells": True,
        "add_noise_stimuli": False,
        "add_hyperpolarizing_stimuli": False,
        "add_relativelinear_stimuli": False,
        "add_pulse_stimuli": False,
        "add_shotnoise_stimuli": False,
        "add_ornstein_uhlenbeck_stimuli": False,
        "add_sinusoidal_stimuli": False,
        "add_linear_stimuli": False,
    }
    if simulation_config_data.get("inputs"):
        params["add_stimuli"] = True
        supported_types = {
            "noise",
            "hyperpolarizing",
            "relativelinear",
            "pulse",
            "sinusoidal",
            "linear",
            "shotnoise",
            "ornstein_uhlenbeck",
        }
        for input_def in simulation_config_data["inputs"].values():
            module = input_def.get("module", "").lower()
            if module not in supported_types:
                logger.warning(
                    "Input type '%s' may not be fully supported by instantiate_gids", module
                )
    if "conditions" in simulation_config_data:
        conditions = simulation_config_data["conditions"]
        if conditions.get("mechanisms"):
            params["add_synapses"] = True
            for mech in conditions["mechanisms"].values():
                if mech.get("minis_single_vesicle", False):
                    params["add_minis"] = True
                    break
    params["add_projections"] = params["add_synapses"]
    return params


def run(
    simulation_config: str | Path,
    simulator: SimulationBackend,
    *,
    libnrnmech_path: Path,
) -> None:
    """Run the simulation with the specified backend.

    The simulation results are saved to the specified results directory.

    Args:
        simulation_config: Path to the simulation configuration file
        simulator: Which simulator to use. Must be one of: 'bluecellulab' or 'neurodamus'.
        libnrnmech_path: Path to mechanisms shared object

    Raises:
        ValueError: If the requested backend is not implemented.
    """
    logger.info("Starting simulation with %s backend", simulator)
    match simulator:
        case SimulationBackend.bluecellulab:
            run_bluecellulab(simulation_config=simulation_config, libnrnmech_path=libnrnmech_path)  # ty:ignore[invalid-argument-type]
        case SimulationBackend.neurodamus:
            run_neurodamus(
                simulation_config=simulation_config,
            )
        case _:
            err_msg = f"Unsupported backend: {simulator}"
            raise ValueError(err_msg)


def run_bluecellulab(
    simulation_config: str | Path,
    *,
    libnrnmech_path: str,
) -> None:
    """Run a simulation using BlueCelluLab backend."""
    with neuron_mpi_process(libnrnmech_path=libnrnmech_path) as process:
        if process.rank == 0:
            logger.info("Initializing BlueCelluLab simulation")

        try:
            config_data = load_json(simulation_config)

            t_stop = config_data["run"]["tstop"]
            dt = config_data["run"]["dt"]
            v_init = config_data["conditions"]["v_init"]

            total_cells, cell_ids_for_this_rank = _distribute_cells(
                config_data, simulation_config, process.rank, process.size
            )
            if not cell_ids_for_this_rank:
                logger.warning("Rank %d: No cells to process", process.rank)

            sim = CircuitSimulation(simulation_config)
            instantiate_params = get_instantiate_gids_params(config_data)

            if process.rank == 0:
                logger.info(
                    "Instantiate arguments from config: %s",
                    " ".join(
                        f"{param}: {value}" for param, value in instantiate_params.items() if value
                    ),
                )
                logger.info("Running BlueCelluLab simulation with %d MPI processes", process.size)
                logger.info(
                    "Total cells: %d, Cells per rank: ~%d",
                    total_cells,
                    total_cells // process.size,
                )
                logger.info("Starting simulation: t_stop=%fms, dt=%fms", t_stop, dt)

        except RuntimeError:
            logger.exception("Error during initialization")
            raise

        logger.info("Rank %d: Processing %d cells ", process.rank, len(cell_ids_for_this_rank))

        try:
            logger.info("Rank %d: Instantiating cells...", process.rank)
            sim.instantiate_gids(cell_ids_for_this_rank, **instantiate_params)  # ty:ignore[invalid-argument-type]

            logger.info("Rank %d: Setting up recordings...", process.rank)
            recording_index, local_sites_index = prepare_recordings_for_reports(
                sim.cells,
                sim.circuit_access.config,
            )

            logger.info("Rank %d: Running simulation...", process.rank)
            sim.run(t_stop, v_init, cvode=False)

            logger.info("Rank %d: Gathering results...", process.rank)
            gathered_sites, all_payload, all_spikes = _gather_results(
                sim=sim,
                process=process,
                recording_index=recording_index,
                cell_ids_for_this_rank=cell_ids_for_this_rank,
                local_sites_index=local_sites_index,
            )

            if process.rank == 0:
                logger.info("Rank %d: Writing reports and ouputs...", process.rank)
                _save_reports_and_outputs(
                    sim=sim,
                    gathered_sites=gathered_sites,
                    all_payload=all_payload,
                    all_spikes=all_spikes,
                )
        except RuntimeError:
            logger.exception("Rank %d failed", process.rank)
            raise

    logger.info("Simulation completed successfully.")


def _distribute_cells(
    config_data: dict[str, Any], simulation_config: str | Path, rank: int, size: int
) -> tuple[int, list[tuple[str, int]]]:
    base_dir = Path(simulation_config).parent
    node_sets_file = base_dir / config_data["node_sets_file"]

    node_set_data = load_json(node_sets_file)

    node_set_name = config_data.get("node_set", "All")
    if node_set_name not in node_set_data:
        err_msg = f"Node set '{node_set_name}' not found in node sets file"
        raise KeyError(err_msg)

    population: str = node_set_data[node_set_name]["population"]
    all_node_ids: list[int] = node_set_data[node_set_name]["node_id"]

    num_nodes = len(all_node_ids)
    nodes_per_rank, remainder = divmod(num_nodes, size)

    start_idx = rank * nodes_per_rank + min(rank, remainder)
    if rank < remainder:
        nodes_per_rank += 1
    end_idx = start_idx + nodes_per_rank

    rank_node_ids = all_node_ids[start_idx:end_idx]
    logger.info("Rank %d node IDs: %s", rank, rank_node_ids)

    return num_nodes, [(population, i) for i in rank_node_ids]


def _gather_results(
    *,
    sim: Any,
    cell_ids_for_this_rank: Any,
    process: MPIProcess,
    recording_index: Any,
    local_sites_index: Any,
) -> tuple[Any, Any, Any]:
    gathered_sites = process.parallel_context.py_gather(local_sites_index, 0)

    local_payload = collect_local_payload(
        sim.cells,
        cell_ids_for_this_rank,
        recording_index,
    )
    local_spikes = collect_local_spikes(sim, cell_ids_for_this_rank)
    all_payload, all_spikes = gather_payload_to_rank0(
        process.parallel_context, local_payload, local_spikes
    )

    return gathered_sites, all_payload, all_spikes


def _save_reports_and_outputs(
    sim: Any,
    gathered_sites: list[Any],
    all_payload: list[dict[Any, Any]],
    all_spikes: dict[str, dict[int, list[float]]],
) -> None:
    all_sites_index = gather_recording_sites(gathered_sites)
    cells_for_writer = payload_to_cells(all_payload, all_sites_index)  # ty:ignore[invalid-argument-type]
    report_mgr = ReportManager(sim.circuit_access.config, sim.dt)  # type: ignore[name-defined]
    report_mgr.write_all(cells=cells_for_writer, spikes_by_pop=all_spikes)


def run_neurodamus(
    simulation_config: str | Path,  # noqa: ARG001
) -> None:
    """Run simulation using Neurodamus backend."""
    logger.warning(
        "Neurodamus backend is not yet implemented. Please use BlueCelluLab backend for now."
    )
    err_msg = "Neurodamus backend is not yet implemented. Please use BlueCelluLab backend for now."
    raise NotImplementedError(err_msg)


def main() -> None:
    """Run simulation via cli."""
    parser = argparse.ArgumentParser(description="Run a BlueCelluLab simulation.")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the simulation configuration file",
    )
    parser.add_argument(
        "--libnrnmech-path",
        type=str,
        required=True,
        help="Path to the nrnmech library",
    )
    parser.add_argument(
        "--simulation-backend", type=str, required=True, help="Simulator backend to use."
    )
    parser.add_argument("--save-nwb", action="store_true", help="Save results in NWB format")

    args = parser.parse_args()

    # Validate simulation config exists
    config_path = Path(args.config)
    if not config_path.exists():
        msg = f"Simulation config file not found: {config_path}"
        raise RuntimeError(msg)

    # Run the simulation
    run(
        simulation_config=args.config,
        simulator=args.simulation_backend,
        libnrnmech_path=args.libnrnmech_path,
    )


if __name__ == "__main__":
    main()

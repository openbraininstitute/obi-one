"""Simulation execution module for OBI-One.

This module provides functionality to run simulations using different backends
(BlueCelluLab, Neurodamus) based on the simulation requirements.
"""

import argparse
import logging
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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

from obi_one.scientific.library.simulation.reporting import (
    save_current_results_to_nwb,
    save_voltage_results_to_nwb,
)
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
    finally:
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


# Type alias for simulator backends
SimulatorBackend = Literal["bluecellulab", "neurodamus"]


def _merge_dicts(list_of_dicts: list[dict]) -> dict:
    return {k: v for d in list_of_dicts for k, v in d.items()}


def _merge_spikes(
    list_of_pop_dicts: list[dict[str, dict[int, list]]],
) -> dict[str, dict[int, list]]:
    out: dict[str, dict[int, list]] = defaultdict(dict)
    for pop_dict in list_of_pop_dicts:
        for pop, gid_map in pop_dict.items():
            out[pop].update(gid_map)
    return out


def _raise_node_set_key_error(node_set_name: str) -> None:
    err_msg = f"Node set '{node_set_name}' not found in node sets file"
    raise KeyError(err_msg)


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
    simulator: SimulatorBackend,
    *,
    libnrnmech_path: Path,
    save_nwb: bool,
) -> None:
    """Run the simulation with the specified backend.

    The simulation results are saved to the specified results directory.

    Args:
        simulation_config: Path to the simulation configuration file
        simulator: Which simulator to use. Must be one of: 'bluecellulab' or 'neurodamus'.
        libnrnmech_path: Path to mechanisms shared object
        save_nwb: Whether to save results in NWB format.

    Raises:
        ValueError: If the requested backend is not implemented.
    """
    logger.info("Starting simulation with %s backend", simulator)
    simulator = simulator.lower()
    if simulator == "bluecellulab":
        run_bluecellulab(
            simulation_config=simulation_config, libnrnmech_path=libnrnmech_path, save_nwb=save_nwb
        )
    elif simulator == "neurodamus":
        run_neurodamus(
            simulation_config=simulation_config,
            save_nwb=save_nwb,
        )
    else:
        err_msg = f"Unsupported backend: {simulator}"
        raise ValueError(err_msg)


def run_bluecellulab(
    simulation_config: str | Path,
    *,
    libnrnmech_path: str,
    save_nwb: bool = False,
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

            if process.rank == 0:
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
            sim.instantiate_gids(cell_ids_for_this_rank, **instantiate_params)

            logger.info("Rank %d: Setting up recordings...", process.rank)
            recording_index, local_sites_index = prepare_recordings_for_reports(
                sim.cells,
                sim.circuit_access.config,
            )

            sim.run(t_stop, v_init, cvode=False)

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

            if process.rank == 0:
                _save_reports_and_outputs(
                    sim=sim,
                    simulation_config=simulation_config,
                    config_data=config_data,
                    gathered_sites=gathered_sites,
                    all_payload=all_payload,
                    all_spikes=all_spikes,
                    save_nwb=save_nwb,
                )
        except RuntimeError:
            logger.exception("Rank %d failed", process.rank)
            raise

    logger.info("Simulation completed successfully.")


def _distribute_cells(
    config_data: dict[str, Any], simulation_config: str | Path, rank: int, size: int
) -> list[tuple[str, int]]:
    base_dir = Path(simulation_config).parent
    node_sets_file = base_dir / config_data["node_sets_file"]

    node_set_data = load_json(node_sets_file)

    node_set_name = config_data.get("node_set", "All")
    if node_set_name not in node_set_data:
        _raise_node_set_key_error(node_set_name)

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


def _save_reports_and_outputs(
    sim: Any,
    simulation_config: str | Path,
    config_data: dict[str, Any],
    gathered_sites,
    all_payload,
    all_spikes,
    *,
    save_nwb: bool = False,
) -> None:
    all_sites_index = gather_recording_sites(gathered_sites)
    cells_for_writer = payload_to_cells(all_payload, all_sites_index)

    all_cell_results = _build_nwb_results_from_cells(
        cells_for_writer,
        simulation_config_data,
    )

    report_mgr = ReportManager(sim.circuit_access.config, sim.dt)  # type: ignore[name-defined]
    report_mgr.write_all(cells=cells_for_writer, spikes_by_pop=all_spikes)

    if not save_nwb:
        return

    output_dir = _resolve_output_dir(simulation_config, config_data)
    output_dir.mkdir(parents=True, exist_ok=True)

    voltage_nwb_path = output_dir / "voltage_report.nwb"
    current_nwb_path = output_dir / "current_report.nwb"

    save_voltage_results_to_nwb(
        all_cell_results,
        execution_id,
        voltage_nwb_path,
    )

    save_current_results_to_nwb(
        all_cell_results,
        execution_id,
        current_nwb_path,
        simulation_config_data,
    )

    # Save voltage traces plot
    plot_path = output_dir / "voltage_traces.png"
    plot_voltage_traces(all_cell_results, plot_path)


def _resolve_output_dir(simulation_config: str | Path, config_data: dict[str, Any]) -> Path:
    # TODO: Can't this be fetched from sim's libsonata config?
    base_dir = Path(simulation_config).parent
    output = config_data.get("output", {})
    if isinstance(output, dict) and (output_dir_str := output.get("output_dir")):
        if output_dir_str.startswith("$OUTPUT_DIR"):
            manifest_base = config_data.get("manifest", {}).get("$OUTPUT_DIR")
            if manifest_base:
                return Path(manifest_base) / output_dir_str.replace("$OUTPUT_DIR/", "")
        return Path(output_dir_str)
    return base_dir / "output"


def _build_nwb_results_from_cells(
    cells: dict[Any, Any],
    simulation_config_data: dict[str, Any],
) -> dict[str, Any]:
    report_meta = _get_report_metadata(simulation_config_data)
    results: dict[str, Any] = {}

    for cell_id, cell in cells.items():
        population = cell_id.population_name
        gid = cell_id.id
        out_key = f"{population}_{gid}"

        try:
            time_ms = np.asarray(cell.get_recording("neuron.h._ref_t"), dtype=float)
        except Exception as exc:
            logger.warning(f"Skipping {out_key}: no time recording found: {exc}")
            continue

        time_s = time_ms / 1000.0
        recordings: Dict[str, Any] = {}

        for report_name, sites in getattr(cell, "report_sites", {}).items():
            meta = report_meta.get(report_name)
            if meta is None:
                continue

            variable_name = meta["variable_name"]
            unit = meta["unit"]

            for site in sites:
                rec_name = site["rec_name"]
                section_name = site["section"]
                segment = float(site["segx"])

                try:
                    values = np.asarray(cell.get_recording(rec_name), dtype=float)
                except Exception as exc:
                    logger.warning(f"Skipping recording '{rec_name}' for {out_key}: {exc}")
                    continue

                recordings[rec_name] = {
                    "variable_name": variable_name,
                    "section": section_name,
                    "segment": segment,
                    "unit": unit,
                    "area_um2": site["area_um2"],
                    "values": values.tolist(),
                }

        results[out_key] = {
            "time": time_s.tolist(),
            "time_unit": "s",
            "recordings": recordings,
        }

    return results


def _get_report_metadata(simulation_config_data: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    reports = simulation_config_data.get("reports", {}) or {}
    out: Dict[str, Dict[str, str]] = {}

    for report_name, report_cfg in reports.items():
        if not report_cfg.get("enabled", True):
            continue
        if report_cfg.get("type") != "compartment":
            continue

        variable_name = report_cfg.get("variable_name")
        if not variable_name:
            continue

        unit = report_cfg.get("unit")
        if unit is None:
            unit = "mV" if variable_name == "v" else "unknown"

        out[report_name] = {
            "variable_name": variable_name,
            "unit": unit,
        }

        out["__default_voltage__"] = {
            "variable_name": "v",
            "unit": "mV",
        }

    return out


def run_neurodamus() -> None:
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
        save_nwb=args.save_nwb,
        simulation_config=args.config,
        simulator=args.simulation_backend,
        libnrnmech_path=args.libnrnmech_path,
    )


if __name__ == "__main__":
    main()

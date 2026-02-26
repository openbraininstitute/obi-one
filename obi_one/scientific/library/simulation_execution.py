"""Simulation execution module for OBI-One.

This module provides functionality to run simulations using different backends
(BlueCelluLab, Neurodamus) based on the simulation requirements.
"""

import json
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import matplotlib.pyplot as plt
import numpy as np
from bluecellulab import CircuitSimulation
from bluecellulab.reports.manager import ReportManager
from neuron import h
from pynwb import NWBHDF5IO, NWBFile
from pynwb.icephys import CurrentClampSeries, IntracellularElectrode

logger = logging.getLogger(__name__)

# Initialize MPI rank
try:
    h.nrnmpi_init()
    pc = h.ParallelContext()
    rank = int(pc.id())
except ImportError:
    rank = 0  # fallback for non-MPI runs
except Exception:
    logger.exception("Error initializing MPI rank")
    rank = 0


def _setup_file_logging() -> logging.Logger:
    """Set up file logging for simulation functions."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"simulation_{timestamp}.log"
    if rank == 0:
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info("File logging initialized. Log file: %s", log_file)
    else:
        logger.info("File logging only on rank 0")
    return logger


# Type alias for simulator backends
SimulatorBackend = Literal["bluecellulab", "neurodamus"]


# ---- merge helpers ---------------------------------------------
def _merge_dicts(list_of_dicts: list[dict[Any, Any]]) -> dict[Any, Any]:
    merged: dict[Any, Any] = {}
    for d in list_of_dicts:
        merged.update(d)
    return merged


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
    simulator: SimulatorBackend = "bluecellulab",
    *,
    save_nwb: bool = False,
) -> None:
    """Run the simulation with the specified backend.

    The simulation results are saved to the specified results directory.

    Args:
        simulation_config: Path to the simulation configuration file
        simulator: Which simulator to use. Must be one of: 'bluecellulab' or 'neurodamus'.
        save_nwb: Whether to save results in NWB format.

    Raises:
        ValueError: If the requested backend is not implemented.
    """
    logger.info("Starting simulation with %s backend", simulator)
    simulator = simulator.lower()
    if simulator == "bluecellulab":
        run_bluecellulab(simulation_config=simulation_config, save_nwb=save_nwb)
    elif simulator == "neurodamus":
        run_neurodamus(
            simulation_config=simulation_config,
            save_nwb=save_nwb,
        )
    else:
        err_msg = f"Unsupported backend: {simulator}"
        raise ValueError(err_msg)


def plot_voltage_traces(
    results: dict[str, Any], output_path: str | Path, max_cols: int = 3
) -> None:
    """Plot voltage traces for all cells in a grid of subplots and save to file."""
    n_cells = len(results)
    if n_cells == 0:
        logger.warning("No voltage traces to plot")
        return
    n_cols = min(max_cols, n_cells)
    n_rows = (n_cells + n_cols - 1) // n_cols
    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(15, 3 * n_rows), squeeze=False, constrained_layout=True
    )
    axes = axes.ravel()
    for idx, (cell_id, trace) in enumerate(results.items()):
        ax = axes[idx]
        time_ms = np.array(trace["time"])
        voltage_mv = np.array(trace["voltage"])
        ax.plot(time_ms, voltage_mv, linewidth=1)
        ax.set_title(f"Cell {cell_id}", fontsize=10)
        ax.grid(visible=True, alpha=0.3)
        if idx >= (n_rows - 1) * n_cols:
            ax.set_xlabel("Time (ms)", fontsize=8)
        if idx % n_cols == 0:
            ax.set_ylabel("mV", fontsize=8)
    for idx in range(n_cells, len(axes)):
        axes[idx].axis("off")
    fig.suptitle(f"Voltage Traces for {n_cells} Cells", fontsize=12)
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved voltage traces plot to %s", output_path)


def save_results_to_nwb(results: dict[str, Any], output_path: str | Path) -> None:
    """Save simulation results to NWB format."""
    try:
        nwbfile = NWBFile(
            session_description="Small Microcircuit Simulation results",
            identifier=str(uuid.uuid4()),
            session_start_time=datetime.now(UTC),
            experimenter="OBI User",
            lab="Virtual Lab",
            institution="OBI",
            experiment_description="Simulation results",
            session_id="small_microcircuit_simulation",
        )
        device = nwbfile.create_device(
            name="SimulatedElectrode", description="Virtual electrode for simulation recording"
        )
        for cell_id, trace in results.items():
            electrode = IntracellularElectrode(
                name=f"electrode_{cell_id}",
                description=f"Simulated electrode for {cell_id}",
                device=device,
                location="soma",
                filtering="none",
            )
            nwbfile.add_icephys_electrode(electrode)
            time_data = np.array(trace["time"], dtype=float) / 1000.0
            voltage_data = np.array(trace["voltage"], dtype=float) / 1000.0
            ics = CurrentClampSeries(
                name=f"voltage_{cell_id}",
                data=voltage_data,
                electrode=electrode,
                timestamps=time_data,
                gain=1.0,
                unit="volts",
                description=f"Voltage trace for {cell_id}",
            )
            nwbfile.add_acquisition(ics)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with NWBHDF5IO(str(output_path), "w") as io:
            io.write(nwbfile)
        logger.info("Successfully saved results to %s", output_path)
    except Exception:
        logger.exception("Error saving results to NWB")
        raise


def run_bluecellulab(
    simulation_config: str | Path,
    *,
    save_nwb: bool = False,
) -> None:
    """Run a simulation using BlueCelluLab backend."""
    logger = _setup_file_logging()
    pc = h.ParallelContext()
    rank, size = int(pc.id()), int(pc.nhost())

    if rank == 0:
        logger.info("Initializing BlueCelluLab simulation")

    try:
        config_data, t_stop, dt = _load_simulation_config(simulation_config)
        cell_ids_for_this_rank = _distribute_cells(config_data, simulation_config, rank, size)
        sim, instantiate_params = _initialize_simulation(config_data, simulation_config, rank)
    except Exception:
        logger.exception("Error during initialization")
        raise

    try:
        _instantiate_and_run(sim, cell_ids_for_this_rank, instantiate_params, t_stop, dt, rank)
        all_traces, all_spikes = _gather_results(sim, cell_ids_for_this_rank, rank, pc)

        if rank == 0:
            _save_reports_and_outputs(
                sim, simulation_config, config_data, all_traces, all_spikes, save_nwb=save_nwb
            )
    except Exception:
        logger.exception("Rank %d failed", rank)
        raise
    finally:
        _finalize(rank, pc)


def _load_simulation_config(simulation_config: str | Path) -> tuple[dict[str, Any], float, float]:
    with Path(simulation_config).open(encoding="utf-8") as f:
        config_data: dict[str, Any] = json.load(f)
    return config_data, config_data["run"]["tstop"], config_data["run"]["dt"]


def _distribute_cells(
    config_data: dict[str, Any], simulation_config: str | Path, rank: int, size: int
) -> list[tuple[str, int]]:
    base_dir = Path(simulation_config).parent
    node_sets_file = base_dir / config_data["node_sets_file"]
    with node_sets_file.open(encoding="utf-8") as f:
        node_set_data: dict[str, Any] = json.load(f)

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

    return [(population, i) for i in rank_node_ids]


def _initialize_simulation(
    config_data: dict[str, Any], simulation_config: str | Path, rank: int
) -> tuple[Any, dict[str, Any]]:
    sim = CircuitSimulation(simulation_config)  # type: ignore[name-defined]
    instantiate_params: dict[str, Any] = get_instantiate_gids_params(config_data)  # type: ignore[name-defined]
    if rank == 0:
        logger.info("Instantiate params: %s", instantiate_params)
    return sim, instantiate_params


def _instantiate_and_run(
    sim: Any,
    cell_ids: list[tuple[str, int]],
    params: dict[str, Any],
    t_stop: float,
    dt: float,
    rank: int,
) -> None:
    logger.info("Rank %d: Instantiating %d cells", rank, len(cell_ids))
    sim.instantiate_gids(cell_ids, **params)
    logger.info("Rank %d: Running simulation...", rank)
    sim.run(t_stop, dt, cvode=False)


def _gather_results(
    sim: Any, cell_ids: list[tuple[str, int]], rank: int, pc: Any
) -> tuple[dict[str, Any], dict[str, dict[int, list[float]]]]:
    time_ms: Any = sim.get_time_trace()
    if time_ms is None:
        logger.error("Rank %d: Time trace is None", rank)
        return {}, {}

    time_s = time_ms / 1000.0
    traces: dict[str, Any] = {}
    spikes: dict[str, dict[int, list[float]]] = defaultdict(dict)

    for pop, gid in cell_ids:
        key = f"{pop}_{gid}"
        voltage = sim.get_voltage_trace((pop, gid))
        if voltage is not None:
            traces[key] = {"time": time_s.tolist(), "voltage": voltage.tolist(), "unit": "mV"}
        spikes[pop][gid] = _get_spikes(sim, (pop, gid))

    gathered_traces = pc.py_gather(traces, 0)
    gathered_spikes = pc.py_gather(spikes, 0)

    if rank == 0:
        return _merge_dicts(gathered_traces), _merge_spikes(gathered_spikes)  # type: ignore[name-defined]
    return {}, {}


def _get_spikes(sim: Any, cell_id: tuple[str, int]) -> list[float]:
    try:
        cell_obj = sim.cells[cell_id]
        spikes: Any = cell_obj.get_recorded_spikes(
            location=sim.spike_location, threshold=sim.spike_threshold
        )
        return list(spikes) if spikes else []
    except (KeyError, AttributeError) as exc:
        logger.debug("No spikes for %s: %s", cell_id, exc)
        return []


def _save_reports_and_outputs(
    sim: Any,
    simulation_config: str | Path,
    config_data: dict[str, Any],
    traces: dict[str, Any],
    spikes: dict[str, dict[int, list[float]]],
    *,
    save_nwb: bool = False,
) -> None:
    report_mgr = ReportManager(sim.circuit_access.config, sim.dt)  # type: ignore[name-defined]
    report_mgr.write_all(cells_or_traces=traces, spikes_by_pop=spikes)

    if not save_nwb:
        return

    output_dir = _resolve_output_dir(simulation_config, config_data)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "results.nwb"
    logger.info("Saving results to %s", output_path)
    save_results_to_nwb(traces, output_path)  # type: ignore[name-defined]

    plot_path = output_dir / "voltage_traces.png"
    plot_voltage_traces(traces, plot_path)  # type: ignore[name-defined]


def _resolve_output_dir(simulation_config: str | Path, config_data: dict[str, Any]) -> Path:
    base_dir = Path(simulation_config).parent
    output = config_data.get("output", {})
    if isinstance(output, dict) and (output_dir_str := output.get("output_dir")):
        if output_dir_str.startswith("$OUTPUT_DIR"):
            manifest_base = config_data.get("manifest", {}).get("$OUTPUT_DIR")
            if manifest_base:
                return Path(manifest_base) / output_dir_str.replace("$OUTPUT_DIR/", "")
        return Path(output_dir_str)
    return base_dir / "output"


def _finalize(rank: int, pc: Any) -> None:
    try:
        logger.info("Rank %d: Cleaning up...", rank)
        pc.barrier()
        if rank == 0:
            logger.info("All ranks completed. Simulation finished.")
    except Exception:
        logger.exception("Error during cleanup in rank %d", rank)


def run_neurodamus() -> None:
    """Run simulation using Neurodamus backend."""
    logger = _setup_file_logging()
    logger.warning(
        "Neurodamus backend is not yet implemented. Please use BlueCelluLab backend for now."
    )
    err_msg = "Neurodamus backend is not yet implemented. Please use BlueCelluLab backend for now."
    raise NotImplementedError(err_msg)

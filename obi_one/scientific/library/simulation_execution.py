"""Simulation execution module for OBI-One.

This module provides functionality to run simulations using different backends
(BlueCelluLab, Neurodamus) based on the simulation requirements.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import matplotlib.pyplot as plt
import numpy as np
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
from pynwb import NWBHDF5IO, H5DataIO, NWBFile
from pynwb.icephys import (
    CurrentClampSeries,
    IntracellularElectrode,
    VoltageClampSeries,
    VoltageClampStimulusSeries,
)

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
    """Plot voltage traces for all cells in a grid of subplots and save to file.

    Args:
        results: Dictionary containing simulation results for each cell
        output_path: Path where to save the plot (should include .png extension)
        max_cols: Maximum number of columns in the subplot grid
    """
    plotted = []
    for cell_id, cell_result in results.items():
        voltage_key = None
        for rec_key, rec in cell_result.get("recordings", {}).items():
            if rec.get("variable_name") == "v":
                voltage_key = rec_key
                break

        if voltage_key is not None:
            plotted.append((cell_id, cell_result, voltage_key))

    n_cells = len(plotted)
    if n_cells == 0:
        logger.warning("No voltage traces to plot")
        return

    # Calculate grid size
    n_cols = min(max_cols, n_cells)
    n_rows = (n_cells + n_cols - 1) // n_cols

    # Create figure with subplots
    fig, axes = plt.subplots(
        n_rows, n_cols, figsize=(15, 3 * n_rows), squeeze=False, constrained_layout=True
    )

    # Flatten axes for easier iteration
    axes = axes.ravel()

    # Plot each cell's voltage trace in its own subplot
    for idx, (cell_id, cell_result, voltage_key) in enumerate(plotted):
        ax = axes[idx]
        time_s = np.asarray(cell_result["time"], dtype=float)
        time_ms = time_s * 1000.0
        voltage_mv = np.asarray(cell_result["recordings"][voltage_key]["values"], dtype=float)

        ax.plot(time_ms, voltage_mv, linewidth=1)
        ax.set_title(f"Cell {cell_id}", fontsize=10)
        ax.grid(visible=True, alpha=0.3)

        # Only label bottom row x-axes
        if idx >= (n_rows - 1) * n_cols:
            ax.set_xlabel("Time (ms)", fontsize=8)

        # Only label leftmost column y-axes
        if idx % n_cols == 0:
            ax.set_ylabel("mV", fontsize=8)

    # Turn off unused subplots
    for idx in range(n_cells, len(axes)):
        axes[idx].axis("off")

    # Add a main title
    fig.suptitle(f"Voltage Traces for {n_cells} Cells", fontsize=12)

    # Save the figure
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved voltage traces plot to %s", output_path)


def _get_report_metadata(simulation_config_data: dict[str, Any]) -> dict[str, dict[str, str]]:
    reports = simulation_config_data.get("reports", {}) or {}
    out: dict[str, dict[str, str]] = {}

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

    return out


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
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping %s: no time recording found: %s", out_key, exc)
            continue

        time_s = time_ms / 1000.0
        recordings: dict[str, Any] = {}

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
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping recording '%s' for %s: %s", rec_name, out_key, exc)
                    continue

                recordings[rec_name] = {
                    "variable_name": variable_name,
                    "section": section_name,
                    "segment": segment,
                    "unit": unit,
                    "area_um2": float(site["area_um2"]),
                    "values": values.tolist(),
                }

        results[out_key] = {
            "time": time_s.tolist(),
            "time_unit": "s",
            "recordings": recordings,
        }

    return results


def save_voltage_results_to_nwb(
    results: dict[str, Any],
    execution_id: str,
    output_path: str | Path,
) -> None:
    """Save voltage report results to NWB format."""
    nwbfile = NWBFile(
        session_description="Small Microcircuit Simulation voltage results",
        identifier=str(uuid.uuid4()),
        session_start_time=datetime.now(UTC),
        experimenter="OBI User",
        lab="Virtual Lab",
        institution="OBI",
        experiment_description="Voltage report results",
        session_id=execution_id,
        was_generated_by=["obi_small_scale_simulator_v1"],
    )

    # Add device and electrode
    device = nwbfile.create_device(
        name="SimulatedElectrode",
        description="Virtual electrode for simulation recording",
    )

    wrote_any = False

    # Add voltage traces
    for cell_id, cell_result in results.items():
        time = np.asarray(cell_result.get("time", []), dtype=float)
        dt = time[1] - time[0]
        voltage_rec = None
        for rec in cell_result.get("recordings", {}).values():
            if rec.get("variable_name") == "v":
                voltage_rec = rec
                break

        if voltage_rec is None:
            logger.warning("Skipping %s: no voltage recording found", cell_id)
            continue

        voltage = np.asarray(voltage_rec.get("values", []), dtype=float)
        n = min(len(time), len(voltage))
        if n < 2:  # noqa: PLR2004
            logger.warning("Skipping %s: voltage/time length mismatch or too short", cell_id)
            continue

        electrode = IntracellularElectrode(
            name=f"electrode_{cell_id}",
            description=f"Simulated electrode for {cell_id}",
            device=device,
            location="soma",
            filtering="none",
        )
        nwbfile.add_icephys_electrode(electrode)

        voltage_data = voltage[:n] / 1000.0  # Convert mV to V
        time_rate = 1.0 / dt

        # Create current clamp series
        ics = CurrentClampSeries(
            name=cell_id,
            data=H5DataIO(data=voltage_data, compression="gzip"),
            electrode=electrode,
            rate=time_rate,
            gain=1.0,
            unit="volts",
            description=f"Voltage trace for {cell_id}",
        )
        nwbfile.add_acquisition(ics)
        wrote_any = True

    if not wrote_any:
        logger.warning("No voltage traces found for NWB export: %s", output_path)
        return

    with NWBHDF5IO(str(output_path), "w") as io:
        io.write(nwbfile)

    logger.info("Saved voltage results to %s", output_path)


def _has_seclamp_input(simulation_config_data: dict[str, Any]) -> bool:
    inputs = simulation_config_data.get("inputs", {}) or {}
    return any(str(v.get("module", "")).lower() == "seclamp" for v in inputs.values())


def _get_seclamp_input_def(simulation_config_data: dict[str, Any]) -> dict[str, Any] | None:
    inputs = simulation_config_data.get("inputs", {}) or {}
    for stim in inputs.values():
        if str(stim.get("module", "")).lower() == "seclamp":
            return stim
    return None


def _reconstruct_seclamp_command(
    simulation_config_data: dict[str, Any],
    time_s: np.ndarray,
) -> np.ndarray | None:
    """Reconstruct SEClamp command waveform in mV from SONATA input config.
    Returns None if no seclamp input exists.
    """
    stim = _get_seclamp_input_def(simulation_config_data)
    if stim is None:
        return None

    t_ms = np.asarray(time_s, dtype=float) * 1000.0

    base_voltage = float(stim["voltage"])
    duration_total = float(stim["duration"])

    durations = stim.get("duration_levels")
    voltages = stim.get("voltage_levels")

    cmd = np.full_like(t_ms, fill_value=base_voltage, dtype=float)

    if durations and voltages:
        durations = [float(x) for x in durations]
        voltages = [float(x) for x in voltages]

        if len(voltages) != len(durations) - 1:
            msg = "Invalid SEClamp config: len(voltage_levels) must equal len(duration_levels) - 1"
            raise ValueError(msg)

        cumulative = np.cumsum(durations)

        if durations[0] == 0 and voltages:
            cmd[t_ms >= 0.0] = voltages[0]

        for idx, level in enumerate(voltages):
            start = cumulative[idx]
            stop = cumulative[idx + 1] if idx + 1 < len(cumulative) else duration_total
            cmd[(t_ms >= start) & (t_ms < stop)] = level

        if voltages:
            cmd[t_ms >= cumulative[len(voltages) - 1]] = voltages[-1]

    return cmd


def save_current_results_to_nwb(  # noqa: PLR0914
    results: dict[str, Any],
    execution_id: str,
    output_path: str | Path,
    simulation_config_data: dict[str, Any],
) -> None:
    nwbfile = NWBFile(
        session_description="Current recordings",
        identifier=str(uuid.uuid4()),
        session_start_time=datetime.now(UTC),
        experimenter="OBI User",
        lab="Virtual Lab",
        institution="OBI",
        experiment_description="Current recordings from simulation",
        session_id=execution_id,
        was_generated_by=["obi_small_scale_simulator_v1"],
    )

    device = nwbfile.create_device(
        name="SimulatedElectrode",
        description="Virtual electrode for simulation recording",
    )

    has_seclamp = _has_seclamp_input(simulation_config_data)
    wrote_any = False

    for cell_id, cell_result in results.items():
        time_s = np.asarray(cell_result["time"], dtype=float)
        if len(time_s) < 2:  # noqa: PLR2004
            continue

        dt_s = time_s[1] - time_s[0]
        if dt_s <= 0:
            continue

        rate_hz = 1.0 / dt_s

        electrode = IntracellularElectrode(
            name=f"electrode_{cell_id}",
            description=f"Simulated electrode for {cell_id}",
            device=device,
            location="soma",
            filtering="none",
        )
        nwbfile.add_icephys_electrode(electrode)

        if has_seclamp:
            cmd_mv = _reconstruct_seclamp_command(simulation_config_data, time_s)
            if cmd_mv is not None:
                stim_ts = VoltageClampStimulusSeries(
                    name=f"{cell_id}__SEClamp",
                    data=H5DataIO(data=(cmd_mv / 1000.0), compression="gzip"),
                    electrode=electrode,
                    rate=rate_hz,
                    gain=1.0,
                    unit="volts",
                    description="SEClamp",
                    stimulus_description="SEClamp",
                )
                nwbfile.add_stimulus(stim_ts)

        for rec in cell_result.get("recordings", {}).values():
            variable_name = rec["variable_name"]
            if variable_name == "v":
                continue

            values = np.asarray(rec["values"], dtype=float)

            section_name = rec["section"]
            segment = rec["segment"]
            area_um2 = float(rec["area_um2"])

            # convert mA/cm2 -> nA
            values_na = values * area_um2 * 0.01

            if "." in variable_name:
                mech, var = variable_name.split(".", 1)
                nwb_var_name = f"{var}_{mech}"
            else:
                nwb_var_name = variable_name

            seg = f"{segment:.3f}".rstrip("0").rstrip(".")
            location = f"{section_name}({seg})"

            ts = VoltageClampSeries(
                name=f"{cell_id}__{nwb_var_name}__{location}",
                data=H5DataIO(data=values_na * 1e-9, compression="gzip"),
                electrode=electrode,
                rate=rate_hz,
                gain=1.0,
                unit="amperes",
                description=nwb_var_name,
                stimulus_description="SEClamp" if has_seclamp else "unknown",
            )

            nwbfile.add_acquisition(ts)

            wrote_any = True

    if not wrote_any:
        logger.warning("No current traces found for NWB export: %s", output_path)
        return

    with NWBHDF5IO(str(output_path), "w") as io:
        io.write(nwbfile)

    logger.info("Saved current NWB to %s", output_path)


def run_bluecellulab(  # noqa: PLR0914
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
        recording_index, local_sites_index = _instantiate_and_run(
            sim, cell_ids_for_this_rank, instantiate_params, t_stop, dt, rank
        )
        gathered_sites = pc.py_gather(local_sites_index, 0)
        local_payload = collect_local_payload(
            sim.cells,
            cell_ids_for_this_rank,
            recording_index,
        )
        local_spikes = collect_local_spikes(sim, cell_ids_for_this_rank)
        all_payload, all_spikes = gather_payload_to_rank0(pc, local_payload, local_spikes)
        if rank == 0:
            all_sites_index = gather_recording_sites(gathered_sites)
            cells_for_writer = payload_to_cells(all_payload, all_sites_index)

            all_cell_results = _build_nwb_results_from_cells(
                cells_for_writer,
                config_data,
            )
            report_mgr = ReportManager(sim.circuit_access.config, sim.dt)
            report_mgr.write_all(cells=cells_for_writer, spikes_by_pop=all_spikes)

            if save_nwb:
                output_dir_str = config_data["output"]["output_dir"]
                output_dir = Path(output_dir_str).resolve()
                output_dir.mkdir(parents=True, exist_ok=True)

                voltage_nwb_path = output_dir / "voltage_report.nwb"
                current_nwb_path = output_dir / "current_report.nwb"

                save_voltage_results_to_nwb(
                    all_cell_results,
                    "execution_id_test",
                    voltage_nwb_path,
                )

                save_current_results_to_nwb(
                    all_cell_results,
                    "execution_id_test",
                    current_nwb_path,
                    config_data,
                )

                plot_path = output_dir / "voltage_traces.png"
                plot_voltage_traces(all_cell_results, plot_path)
                logger.info("Successfully saved voltage traces plot to %s", plot_path)

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
    recording_index, local_sites_index = prepare_recordings_for_reports(
        sim.cells,
        sim.circuit_access.config,
    )
    logger.info("Rank %d: Running simulation...", rank)
    sim.run(t_stop, dt, cvode=False)

    return recording_index, local_sites_index


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

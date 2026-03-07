import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from pynwb import NWBHDF5IO, H5DataIO, NWBFile
from pynwb.icephys import (
    CurrentClampSeries,
    IntracellularElectrode,
    VoltageClampSeries,
    VoltageClampStimulusSeries,
)

logger = logging.getLogger(__name__)

DEFAULT_AGENT_NAME = "obi_small_scale_simulator_v1"
CURRENT_REPORT_WRITER_AGENT_NAME = "obi_small_scale_simulator_v1__current_report_writer"


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
        was_generated_by=[DEFAULT_AGENT_NAME],
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
        voltage_rec = None
        for rec in cell_result.get("recordings", {}).values():
            if rec.get("variable_name") == "v":
                voltage_rec = rec
                break

        if voltage_rec is None:
            logger.warning("Skipping %d: no voltage recording found", cell_id)
            continue

        voltage = np.asarray(voltage_rec.get("values", []), dtype=float)
        n = min(len(time), len(voltage))
        if n < 2:  # noqa: PLR2004
            logger.warning("Skipping %d: voltage/time length mismatch or too short", cell_id)
            continue

        dt = time[1] - time[0]

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

    # Save to file
    with NWBHDF5IO(str(output_path), "w") as io:
        io.write(nwbfile)

    logger.info("Saved voltage results to %s", output_path)


def save_current_results_to_nwb(  # noqa: C901, PLR0914, PLR0915
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
        was_generated_by=[CURRENT_REPORT_WRITER_AGENT_NAME],
    )

    device = nwbfile.create_device(
        name="SimulatedElectrode",
        description="Virtual electrode for simulation recording",
    )

    has_seclamp = _has_seclamp_input(simulation_config_data)
    wrote_any = False
    sweep_no = 0

    for cell_id, cell_result in results.items():
        time_s = np.asarray(cell_result["time"], dtype=float)
        if len(time_s) < 2:  # noqa: PLR2004
            logger.warning("Skipping %d: not enough time points", cell_id)
            continue

        dt_s = time_s[1] - time_s[0]
        if dt_s <= 0:
            logger.warning("Skipping %d: non-positive dt", cell_id)
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
                    name=f"{cell_id}__vcss__sweep__{sweep_no:03d}",
                    data=H5DataIO(data=(cmd_mv / 1000.0), compression="gzip"),
                    electrode=electrode,
                    rate=rate_hz,
                    gain=1.0,
                    unit="volts",
                    description="SEClamp",
                    stimulus_description="SEClamp",
                    sweep_number=sweep_no,
                )
                nwbfile.add_stimulus(stim_ts)

        for rec_key, rec in cell_result.get("recordings", {}).items():
            variable_name = rec["variable_name"]
            if variable_name == "v":
                continue

            values = np.asarray(rec["values"], dtype=float)
            if values.size == 0:
                logger.warning("Skipping empty recording '%s' for %d", rec_key, cell_id)
                continue

            section_name = rec["section"]
            segment = rec["segment"]
            area_um2 = rec["area_um2"]

            if area_um2 is None:
                logger.warning("Skipping '%s' for %d: missing area_um2, rec_key, cell_id")
                continue
            area_um2 = float(area_um2)

            # convert mA/cm2 -> nA
            values_nA = values * area_um2 * 0.01  # noqa: N806

            if "." in variable_name:
                mech, var = variable_name.split(".", 1)
                nwb_var_name = f"{var}_{mech}"
            else:
                nwb_var_name = variable_name

            seg = f"{segment:.3f}".rstrip("0").rstrip(".")
            location = f"{section_name}({seg})"

            ts = VoltageClampSeries(
                name=f"{cell_id}__vcs__{nwb_var_name}__{location}__sweep__{sweep_no:03d}",
                data=H5DataIO(data=values_nA * 1e-9, compression="gzip"),
                electrode=electrode,
                rate=rate_hz,
                gain=1.0,
                unit="amperes",
                description=nwb_var_name,
                stimulus_description="SEClamp" if has_seclamp else "unknown",
                sweep_number=sweep_no,
            )

            nwbfile.add_acquisition(ts)
            wrote_any = True

    if not wrote_any:
        msg = f"No current traces found for NWB export: {output_path}"
        logger.warning(msg)
        return

    with NWBHDF5IO(str(output_path), "w") as io:
        io.write(nwbfile)

    msg = f"Saved current NWB to {output_path}"
    logger.info(msg)


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

        if len(voltages) != len(durations):
            msg = "Invalid SEClamp config: len(voltages) must equal len(durations)"
            raise ValueError(msg)

        cumulative = np.cumsum(durations)

        if durations[0] == 0 and voltages:
            cmd[t_ms >= 0.0] = voltages[0]

        for idx, level in enumerate(voltages):
            start = cumulative[idx]
            stop = cumulative[idx + 1] if idx + 1 < len(cumulative) else duration_total
            cmd[(t_ms >= start) & (t_ms < stop)] = level

        # ensure last level holds until duration_total
        if voltages:
            cmd[t_ms >= cumulative[len(voltages) - 1]] = voltages[-1]

    return cmd


def _get_seclamp_input_def(simulation_config_data: dict[str, Any]) -> dict[str, Any] | None:
    inputs = simulation_config_data.get("inputs", {}) or {}
    for stim in inputs.values():
        if str(stim.get("module", "")).lower() == "seclamp":
            return stim
    return None


def _has_seclamp_input(simulation_config_data: dict[str, Any]) -> bool:
    inputs = simulation_config_data.get("inputs", {}) or {}
    return any(str(v.get("module", "")).lower() == "seclamp" for v in inputs.values())

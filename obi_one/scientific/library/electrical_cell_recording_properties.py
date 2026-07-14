"""Helpers for inspecting ``ElectricalCellRecording`` entities.

Exposes the set of protocol names present in each recording's NWB asset and
the per-protocol step amplitudes (in nA) — both consumed by the e-feature
extraction stage so the user never has to type protocol metadata that's
already in the file.
"""

import logging
import tempfile
from pathlib import Path

import h5py
import numpy as np
from scipy.ndimage import median_filter

L = logging.getLogger(__name__)

# Stimulus-onset detection constants, mirroring ``bluepyefe.ecode.step``.
_ONSET_SMOOTH_WIDTH = 85
_ONSET_NOISE_SAMPLES = 50
_ONSET_THRESHOLD_FACTOR = 4.5
_ONSET_THRESHOLD_FLOOR_NA = 1e-5
_ONSET_BUFFER_MS = 2.0
_BASELINE_WINDOW = 300
_MIN_ONSET_SAMPLES = 100


def read_protocols_from_nwb(nwb_path: Path) -> list[str]:
    """Return the sorted protocol (ecode) names stored in an NWB file.

    For BBP-style NWBs the protocol names live under ``data_organization/<cell>/<ecode>``.
    For other formats we fall back to parsing the ``ccs__<ECODE>__<idx>`` /
    ``ic__<ECODE>__<idx>`` keys in ``acquisition``.
    """
    min_parts_for_protocol = 2
    protocols: set[str] = set()
    with h5py.File(str(nwb_path), "r") as f:
        if "data_organization" in f:
            for cell_id in f["data_organization"]:
                protocols.update(f["data_organization"][cell_id].keys())
        elif "acquisition" in f:
            for key in f["acquisition"]:
                parts = key.split("__")
                if len(parts) >= min_parts_for_protocol:
                    protocols.add(parts[1])
    return sorted(protocols)


def get_recording_protocols(
    recording_ids: list[str],
    db_client: object,
) -> dict[str, list[str]]:
    """Return ``{recording_id: [protocol_name, ...]}`` for each recording.

    Downloads each recording's NWB asset via the entitysdk client and reads
    the protocol (ecode) names from it using :func:`read_protocols_from_nwb`.
    """
    from obi_one.scientific.from_id.electrical_cell_recording_from_id import (  # noqa: PLC0415
        ElectricalCellRecordingFromID,
    )

    by_recording: dict[str, list[str]] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        for rid in recording_ids:
            recording = ElectricalCellRecordingFromID(id_str=rid)
            nwb_path = recording.download_asset(
                dest_dir=Path(tmpdir), db_client=db_client
            )
            by_recording[rid] = read_protocols_from_nwb(nwb_path)
    return by_recording


def _stim_key_for_trace(trace_name: str) -> str | None:
    """Map a BBP voltage trace name to its sibling current trace key.

    The key is in ``stimulus/presentation``.
    """
    if "ccs_" in trace_name:
        return trace_name.replace("ccs_", "ccss_")
    if "ic_" in trace_name:
        return trace_name.replace("ic_", "ics_")
    return None


def _step_amplitude_na(current_a: np.ndarray) -> float:
    """Estimate the step amplitude (nA) of a current trace.

    Baseline = median of the first 5%, step = median of the middle 40%, amp
    is their difference converted from amperes to nanoamperes. Mirrors what
    ``bluepyefe.ecode.step.Step`` extracts when ``ton``/``toff`` are absent.
    """
    n = len(current_a)
    if n == 0:
        return 0.0
    baseline = float(np.median(current_a[: max(1, n // 20)]))
    step = float(np.median(current_a[int(n * 0.3) : int(n * 0.7)]))
    return (step - baseline) * 1e9


def _read_amplitudes_from_nwb(
    nwb_path: Path,
    protocol_names: list[str],
    *,
    round_decimals: int = 3,
) -> dict[str, list[float]]:
    """Return ``{protocol_name: [step_amplitude_nA, ...]}`` for the requested protocols.

    Inspects every sweep under each ``data_organization/<cell>/<protocol>``
    group (BBP layout), reads its sibling current trace from
    ``stimulus/presentation``, estimates the step amplitude with
    :func:`_step_amplitude_na`, rounds to ``round_decimals`` decimal places
    (default 3 → 1 pA precision) and dedupes.
    """
    requested = set(protocol_names)
    amps: dict[str, set[float]] = {p: set() for p in protocol_names}
    with h5py.File(str(nwb_path), "r") as f:  # noqa: PLR1702
        if "data_organization" not in f or "stimulus" not in f:
            return {p: [] for p in protocol_names}
        stim_pres = f["stimulus"]["presentation"]
        for cell_id in f["data_organization"]:
            cell = f["data_organization"][cell_id]
            for protocol_name in cell:
                if protocol_name not in requested:
                    continue
                for rep in cell[protocol_name]:
                    for sweep in cell[protocol_name][rep]:
                        for trace_name in cell[protocol_name][rep][sweep]:
                            key_current = _stim_key_for_trace(trace_name)
                            if key_current is None or key_current not in stim_pres:
                                continue
                            data = stim_pres[key_current]["data"]
                            conversion = data.attrs.get("conversion", 1.0)
                            current_a = np.asarray(data[()]) * conversion
                            amp_na = _step_amplitude_na(current_a)
                            amps[protocol_name].add(round(amp_na, round_decimals))
    return {p: sorted(v) for p, v in amps.items()}


def _detect_ton_ms(current_na: np.ndarray, dt_ms: float) -> float | None:
    """Stimulus onset (ms) à la ``bluepyefe.ecode.step``.

    Returns the time of the first sample where the smoothed current departs the
    pre-stimulus baseline by more than a noise-scaled threshold, or ``None`` if
    the trace is too short or no onset is detectable.
    """
    n = len(current_na)
    if n < _MIN_ONSET_SAMPLES or dt_ms <= 0:
        return None
    smooth = median_filter(current_na, size=_ONSET_SMOOTH_WIDTH)
    edges = np.concatenate(
        (current_na[:_ONSET_NOISE_SAMPLES], current_na[-_ONSET_NOISE_SAMPLES:]),
    )
    threshold = max(_ONSET_THRESHOLD_FACTOR * float(np.std(edges)), _ONSET_THRESHOLD_FLOOR_NA)
    buffer_idx = max(1, int(_ONSET_BUFFER_MS / dt_ms))
    baseline = float(
        np.median(median_filter(current_na[: min(_BASELINE_WINDOW, n)], size=_ONSET_SMOOTH_WIDTH)),
    )
    above = np.abs(np.asarray(smooth[buffer_idx:]) - baseline) > threshold
    if not above.any():
        return None
    return (buffer_idx + int(np.argmax(above))) * dt_ms


def _detect_protocol_ton_ms(protocol_group: h5py.Group, stim_pres: h5py.Group) -> float | None:
    """Detect ``ton`` (ms) from the first usable current trace under a
    ``data_organization`` protocol group, or ``None`` if not detectable.
    """
    for rep in protocol_group:
        for sweep in protocol_group[rep]:
            for trace_name in protocol_group[rep][sweep]:
                key_current = _stim_key_for_trace(trace_name)
                if key_current is None or key_current not in stim_pres:
                    continue
                series = stim_pres[key_current]
                rate = (
                    series["starting_time"].attrs.get("rate") if "starting_time" in series else None
                )
                if not rate:
                    continue
                data = series["data"]
                conversion = data.attrs.get("conversion", 1.0)
                current_na = np.asarray(data[()]) * conversion * 1e9
                ton = _detect_ton_ms(current_na, 1000.0 / float(rate))
                if ton is not None:
                    return ton
    return None


def _read_timing_from_nwb(
    nwb_path: Path,
    protocol_names: list[str],
) -> dict[str, float]:
    """Return ``{protocol_name: ton_ms}`` for the requested protocols.

    ``ton`` is the stimulus onset detected from the current waveform the same way
    bluepyefe's ``Step`` eCode detects it. Used to supply ``ton`` to eCodes (e.g.
    ``Ramp``) that require it instead of auto-detecting it. Protocols with no
    detectable onset are omitted.
    """
    requested = set(protocol_names)
    timing: dict[str, float] = {}
    with h5py.File(str(nwb_path), "r") as f:
        if "data_organization" not in f or "stimulus" not in f:
            return {}
        stim_pres = f["stimulus"]["presentation"]
        for cell_id in f["data_organization"]:
            cell = f["data_organization"][cell_id]
            for protocol_name in cell:
                if protocol_name not in requested or protocol_name in timing:
                    continue
                ton = _detect_protocol_ton_ms(cell[protocol_name], stim_pres)
                if ton is not None:
                    timing[protocol_name] = ton
    return timing

"""Helpers for inspecting ``ElectricalCellRecording`` entities.

Exposes the set of protocol names present in each recording's NWB asset and
the per-protocol step amplitudes (in nA) — both consumed by the e-feature
extraction stage so the user never has to type protocol metadata that's
already in the file.
"""

import logging
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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
            for key, series in f["acquisition"].items():
                description = series.attrs.get("stimulus_description")
                if isinstance(description, bytes):
                    description = description.decode("utf-8")
                if description:
                    protocols.add(description)
                    continue
                parts = key.split("__")
                if len(parts) >= min_parts_for_protocol:
                    protocols.add(parts[1])
    return sorted(protocols)


def stim_key_for_trace(trace_name: str) -> str | None:
    """Map a BBP voltage trace name to its sibling current trace key.

    The key is in ``stimulus/presentation``.
    """
    if "ccs_" in trace_name:
        return trace_name.replace("ccs_", "ccss_")
    if "ic_" in trace_name:
        return trace_name.replace("ic_", "ics_")
    return None


def _unit_str(unit: object) -> str:
    """Decode an NWB/reader unit to ``str``; defaults to amperes when absent."""
    if isinstance(unit, bytes):
        unit = unit.decode("utf-8")
    return str(unit) if unit else "A"


def bbp_current_conversion(
    current_attrs: Mapping[str, Any],
    voltage_attrs: Mapping[str, Any] | None,
) -> tuple[float, str]:
    """Return ``(conversion, unit)`` for a BBP NWB current series.

    Mirrors the unit-mixup repair in bluepyefe's ``BBPNWBReader``: when both
    series are labelled ``volts`` with voltage ``conversion == 1e-12`` and
    current ``conversion == 0.001``, the current is really in pA-scaled amperes.
    """
    i_conversion = float(current_attrs.get("conversion", 1.0))
    i_unit = _unit_str(current_attrs.get("unit"))
    if voltage_attrs is not None:
        v_conversion = float(voltage_attrs.get("conversion", 1.0))
        v_unit = _unit_str(voltage_attrs.get("unit"))
        if (
            math.isclose(v_conversion, 1e-12)
            and math.isclose(i_conversion, 1e-3)
            and v_unit == "volts"
            and i_unit == "volts"
        ):
            return 1e-12, "amperes"
    return i_conversion, i_unit


def step_amplitude(current: np.ndarray) -> float:
    """Estimate the step amplitude of a current trace, in its native unit.

    Baseline = median of the first 5%, step = median of the middle 40%, amp
    is their difference. Mirrors what ``bluepyefe.ecode.step.Step`` extracts
    when ``ton``/``toff`` are absent.
    """
    n = len(current)
    if n == 0:
        return 0.0
    baseline = float(np.median(current[: max(1, n // 20)]))
    step = float(np.median(current[int(n * 0.3) : int(n * 0.7)]))
    return step - baseline


def estimate_step_amplitude(current: np.ndarray) -> float:
    """Estimate the step amplitude of a current trace, in its native unit.

    Baseline = median of the first 5%; the step samples are those deviating from
    baseline by more than half the peak deviation; amp is their median minus
    baseline. Unlike :func:`step_amplitude`, this does not assume the step
    covers the middle of the trace.
    """
    current = np.asarray(current, dtype=float)
    n = len(current)
    if n == 0:
        return 0.0
    baseline = float(np.median(current[: max(1, n // 20)]))
    deviation = np.abs(current - baseline)
    peak = float(deviation.max())
    if peak <= 0:
        return 0.0
    step = float(np.median(current[deviation > 0.5 * peak]))
    return step - baseline


def read_amplitudes_via_inspection(
    nwb_path: Path,
    protocol_names: list[str] | None = None,
    *,
    round_decimals: int = 3,
) -> dict[str, list[float]]:
    """Return ``{protocol_name: [step_amplitude_nA, ...]}`` via bluepyefe's readers.

    Fallback for NWB layouts without a ``data_organization`` group (Scala, AIBS,
    TRT, VU): protocol names and current traces come from
    :func:`bluepyefe.reader.inspect_nwb` — the same names bluepyefe reports at
    extraction time. Current traces are converted with
    :func:`bluepyefe.tools.to_nA` using each trace's ``i_unit``, and amplitudes
    are estimated with :func:`estimate_step_amplitude`. Traces whose unit
    ``to_nA`` does not recognise are skipped. Empty dict on unreadable files or
    when bluepyefe is not installed.

    When ``protocol_names`` is given, only file protocols belonging to a
    requested ``Protocol`` class (via ``protocol_class_name_for``) are
    inspected — e.g. requested ``step`` matches the file's ``GenericStep``,
    while unrelated protocols in the same file are excluded.
    """
    try:
        from bluepyefe.reader import (  # ruff: ignore[import-outside-top-level]
            NWBInspectionError,
            inspect_nwb,
        )
        from bluepyefe.tools import to_nA  # ruff: ignore[import-outside-top-level]
    except ImportError:
        return {}
    try:
        protocols = inspect_nwb(nwb_path)["protocols"]
    except (OSError, NWBInspectionError):
        L.warning("bluepyefe could not inspect NWB file %s", nwb_path)
        return {}
    if protocol_names is not None:
        from obi_one_lazy.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
            protocol_class_name_for,
        )

        wanted = {cls for p in protocol_names if (cls := protocol_class_name_for(p))}
        protocols = [p for p in protocols if protocol_class_name_for(p) in wanted]
    amps: dict[str, list[float]] = {}
    for protocol_name in protocols:
        try:
            traces = inspect_nwb(nwb_path, protocol_names=[protocol_name])["traces"]
        except (OSError, NWBInspectionError):
            continue
        values: set[float] = set()
        for t in traces:
            current = np.asarray(t["current"], dtype=float)
            try:
                current_na = to_nA(current, _unit_str(t.get("i_unit")))
            except Exception:  # ruff: ignore[blind-except]
                L.warning(
                    "Skipping trace %s of %s: unknown current unit %r",
                    t.get("id"),
                    nwb_path,
                    t.get("i_unit"),
                )
                continue
            values.add(round(estimate_step_amplitude(current_na), round_decimals))
        amps[protocol_name] = sorted(values)
    return amps


def read_amplitudes_from_nwb(
    nwb_path: Path,
    protocol_names: list[str],
    *,
    round_decimals: int = 3,
) -> dict[str, list[float]]:
    """Return ``{protocol_name: [step_amplitude_nA, ...]}`` for the requested protocols.

    Inspects every sweep under each ``data_organization/<cell>/<protocol>``
    group (BBP layout), reads its sibling current trace from
    ``stimulus/presentation``, converts it to nA with
    :func:`bluepyefe.tools.to_nA` (using the series' ``unit`` attr, default A,
    with bluepyefe's volts/volts mixup repair via :func:`bbp_current_conversion`),
    estimates the step amplitude with :func:`step_amplitude`, rounds to
    ``round_decimals`` decimal places
    (default 3 → 1 pA precision) and dedupes.

    Files without the BBP ``data_organization`` layout are handled by
    :func:`read_amplitudes_via_inspection`, which reports amplitudes keyed by
    the protocol names bluepyefe's readers use, limited to the requested
    protocol classes.
    """
    requested = set(protocol_names)
    amps: dict[str, set[float]] = {p: set() for p in protocol_names}
    with h5py.File(str(nwb_path), "r") as f:  # ruff: ignore[too-many-nested-blocks]
        if "data_organization" not in f or "stimulus" not in f:
            return read_amplitudes_via_inspection(
                nwb_path, protocol_names, round_decimals=round_decimals
            )
        from bluepyefe.tools import to_nA  # ruff: ignore[import-outside-top-level]

        stim_pres = f["stimulus"]["presentation"]
        acquisition = f.get("acquisition")
        for cell_id in f["data_organization"]:
            cell = f["data_organization"][cell_id]
            for protocol_name in cell:
                if protocol_name not in requested:
                    continue
                for rep in cell[protocol_name]:
                    for sweep in cell[protocol_name][rep]:
                        for trace_name in cell[protocol_name][rep][sweep]:
                            key_current = stim_key_for_trace(trace_name)
                            if key_current is None or key_current not in stim_pres:
                                continue
                            data = stim_pres[key_current]["data"]
                            voltage = acquisition.get(trace_name) if acquisition else None
                            voltage_attrs = (
                                voltage["data"].attrs
                                if isinstance(voltage, h5py.Group) and "data" in voltage
                                else None
                            )
                            conversion, unit = bbp_current_conversion(data.attrs, voltage_attrs)
                            current = np.asarray(data[()], dtype=float) * conversion
                            try:
                                current_na = to_nA(current, unit)
                            except Exception:  # ruff: ignore[blind-except]
                                L.warning(
                                    "Skipping stimulus %s of %s: unknown current unit %r",
                                    key_current,
                                    nwb_path,
                                    unit,
                                )
                                continue
                            amps[protocol_name].add(
                                round(step_amplitude(current_na), round_decimals)
                            )
    return {p: sorted(v) for p, v in amps.items()}


def detect_ton_ms(current_na: np.ndarray, dt_ms: float) -> float | None:
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


def detect_protocol_ton_ms(protocol_group: h5py.Group, stim_pres: h5py.Group) -> float | None:
    """Detect ``ton`` (ms) from the first usable current trace under a
    ``data_organization`` protocol group, or ``None`` if not detectable.
    """
    for rep in protocol_group:
        for sweep in protocol_group[rep]:
            for trace_name in protocol_group[rep][sweep]:
                key_current = stim_key_for_trace(trace_name)
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
                ton = detect_ton_ms(current_na, 1000.0 / float(rate))
                if ton is not None:
                    return ton
    return None


def read_timing_from_nwb(
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
                ton = detect_protocol_ton_ms(cell[protocol_name], stim_pres)
                if ton is not None:
                    timing[protocol_name] = ton
    return timing

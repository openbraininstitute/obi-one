"""Helpers for inspecting ``ElectricalCellRecording`` entities.

Exposes the set of protocol names present in each recording's NWB asset and
the per-protocol step amplitudes (in nA) — both consumed by the e-feature
extraction stage so the user never has to type protocol metadata that's
already in the file.
"""

import itertools
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


# NWB type of a current-clamp stimulus; voltage clamp uses ``VoltageClampStimulusSeries``.
_CURRENT_CLAMP_STIMULUS_TYPE = "CurrentClampStimulusSeries"
# Current units ``bluepyefe.tools.to_nA`` accepts (case-insensitive for amperes only).
_AMPERE_UNITS = frozenset({"a", "amperes", "amps"})
_SCALED_CURRENT_UNITS = frozenset({"mA", "uA", "nA", "pA"})


def is_current_clamp_stimulus(neurodata_type: object, unit: str) -> bool:
    """Whether a stimulus series injects current, i.e. was recorded in current clamp.

    Every bluepyefe/BluePyEModel eCode is a current-clamp stimulus. The NWB type of
    the series decides when present; otherwise (legacy files, bluepyefe reader
    traces) the unit must be a current unit — a voltage-clamp command is in volts.
    """
    if isinstance(neurodata_type, bytes):
        neurodata_type = neurodata_type.decode("utf-8")
    if neurodata_type:
        return neurodata_type == _CURRENT_CLAMP_STIMULUS_TYPE
    return unit.lower() in _AMPERE_UNITS or unit in _SCALED_CURRENT_UNITS


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


def _onset_threshold(smooth: np.ndarray) -> float:
    """Noise-scaled change threshold (nA), as ``bluepyefe.ecode.step`` derives it."""
    edges = np.concatenate((smooth[:_ONSET_NOISE_SAMPLES], smooth[-_ONSET_NOISE_SAMPLES:]))
    return max(_ONSET_THRESHOLD_FACTOR * float(np.std(edges)), _ONSET_THRESHOLD_FLOOR_NA)


def _holding_current(smooth: np.ndarray, threshold: float) -> float:
    """Pre-stimulus holding current (nA) of a median-filtered trace.

    The median of bluepyefe's ``base_current`` window (the first
    ``_BASELINE_WINDOW`` samples), cut at the first sample departing from the
    trace's start by more than ``threshold`` so a stimulus starting inside the
    window does not leak into it.
    """
    head = smooth[:_BASELINE_WINDOW]
    departed = np.flatnonzero(np.abs(head - head[0]) > threshold)
    end = int(departed[0]) if departed.size else len(head)
    return float(np.median(head[: max(1, end)]))


def plateau_levels(current: np.ndarray) -> list[float]:
    """Non-baseline plateau levels of a current trace, in time order, in nA.

    Segments the median-filtered trace wherever the smoothed derivative exceeds
    a noise-scaled threshold (mirroring ``bluepyefe.ecode.step``'s onset
    detection), keeps segments at least ~1% of the trace long, and returns each
    plateau's level relative to the pre-stimulus holding current — e.g. ``[amp,
    amp2, amp]`` for an sAHP two-step or ``[depol, hyperpol]`` for a
    DeHyperPol.
    """
    n = len(current)
    if n < _MIN_ONSET_SAMPLES:
        return []
    smooth = median_filter(np.asarray(current, dtype=float), size=_ONSET_SMOOTH_WIDTH)
    threshold = _onset_threshold(smooth)
    baseline = _holding_current(smooth, threshold)
    bounds = np.concatenate(([0], np.flatnonzero(np.abs(np.diff(smooth)) > threshold) + 1, [n]))
    min_len = max(_ONSET_SMOOTH_WIDTH, n // 100)
    levels: list[float] = []
    for a, b in itertools.pairwise(bounds):
        if b - a < min_len:
            continue
        level = float(np.median(smooth[a:b])) - baseline
        if abs(level) > threshold:
            levels.append(level)
    return levels


# Samples before the smoothed peak that bluepyefe's ``Ramp`` takes the amplitude from.
_RAMP_PEAK_SAMPLES = 10


def _peak_amplitude(current: np.ndarray, shape: str) -> float:
    """The ``amp`` of a peak-shaped eCode, relative to the holding current, in nA.

    Mirrors each bluepyefe eCode: ``ramp`` takes the median of the raw samples
    just before the smoothed maximum, ``posCheops``/``sineSpec`` the smoothed
    maximum, ``negCheops`` the smoothed minimum, and ``pinkNoise``/``capCheck``
    the largest absolute raw deviation (unsigned).
    """
    current = np.asarray(current, dtype=float)
    if len(current) == 0:
        return 0.0
    smooth = median_filter(current, size=_ONSET_SMOOTH_WIDTH)
    baseline = _holding_current(smooth, _onset_threshold(smooth))
    if shape == "ramp":
        peak = max(1, int(np.argmax(smooth)))
        return float(np.median(current[max(0, peak - _RAMP_PEAK_SAMPLES) : peak])) - baseline
    if shape == "negcheops":
        return float(np.min(smooth)) - baseline
    if shape in {"pinknoise", "capcheck"}:
        return float(np.max(np.abs(current - baseline)))
    return float(np.max(smooth)) - baseline


# eCodes whose ``amp`` is a peak (or trough) rather than a step level.
_PEAK_AMPLITUDE_SHAPES = frozenset(
    {"ramp", "negcheops", "poscheops", "sinespec", "pinknoise", "capcheck"}
)


def estimate_matchable_amplitude(
    current_na: np.ndarray, ecode_class: str | None, dt_ms: float | None = None
) -> tuple[float | None, float | None]:
    """Return ``(matchable_amp, secondary_amp)`` of one sweep, in nA.

    ``matchable_amp`` is the amplitude the eCode's ``in_target`` compares (its
    ``amp``, or ``amp2`` for the sAHP family), and ``secondary_amp`` the other
    level of a two-step stimulus:

    * ``Step`` (and unknown shapes): the step level;
    * ``SAHP`` two-step family: the *short middle* step (``amp2``) — the long
      step is ``secondary_amp``;
    * ``HyperDePol`` and ``DeHyperPol``: the *first* step (both use the base
      ``in_target`` on ``amp``) — the second step is ``secondary_amp``;
    * ramp/cheops/sinespec/pinknoise/capcheck: the peak, as each eCode defines it;
    * ``SpikeRec``: ``None`` — it matches a ms ``delta``, not an amplitude.

    With the sampling interval ``dt_ms``, the plateaus are those
    :func:`detect_stimulus_timing` finds; without it, :func:`plateau_levels`'s, which
    misses steps when the rest before the stimulus is short.
    """
    shape = (ecode_class or "Step").lower()
    if shape == "spikerec":
        return None, None
    if shape in _PEAK_AMPLITUDE_SHAPES:
        return _peak_amplitude(current_na, shape), None
    levels = (
        plateau_levels(current_na)
        if dt_ms is None
        else [level for _, _, level in _plateaus(np.asarray(current_na, dtype=float), dt_ms)[0]]
    )
    first = levels[0] if levels else None
    second = levels[1] if len(levels) > 1 else None
    if shape == "sahp":
        # sAHP targets its second plateau, the short middle step; the long step
        # around it is secondary.
        matchable, secondary = (second, first) if second is not None else (first, None)
    elif first is not None:
        # Step, HyperDePol and DeHyperPol target the first plateau.
        matchable, secondary = first, second
    else:
        matchable, secondary = step_amplitude(current_na), None
    return matchable, secondary


def ecode_class_for(protocol_name: str) -> str | None:
    """The ``ecode_class`` of the ``Protocol`` matching a file protocol name."""
    from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
        protocol_class_for,
    )

    cls = protocol_class_for(protocol_name)
    return getattr(cls, "ecode_class", None) if cls is not None else None


def read_amplitudes_via_inspection(
    nwb_path: Path,
    protocol_names: list[str] | None = None,
    *,
    round_decimals: int = 3,
) -> dict[str, dict[str, Any]]:
    """Return ``{protocol_name: {"matchable": [...], "secondary": [...], "timing": {...}}}``.

    Amplitudes are in nA; ``timing`` maps each detected timing key to its distinct
    values in ms (see :func:`detect_stimulus_timing` and :func:`distinct_times`).

    Fallback for NWB layouts without a ``data_organization`` group (Scala, AIBS,
    TRT, VU): protocol names and current traces come from
    :func:`bluepyefe.reader.inspect_nwb` — the same names bluepyefe reports at
    extraction time. Current traces are converted with
    :func:`bluepyefe.tools.to_nA` using each trace's ``i_unit``, and amplitudes
    are estimated with :func:`estimate_matchable_amplitude` using each
    protocol's eCode shape. Traces whose unit is not a current unit (not current
    clamp, see :func:`is_current_clamp_stimulus`) are skipped. Empty dict on
    unreadable files or when bluepyefe is not installed.

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
    except ImportError:
        return {}
    try:
        protocols = inspect_nwb(nwb_path)["protocols"]
    except (OSError, NWBInspectionError):
        L.warning("bluepyefe could not inspect NWB file %s", nwb_path)
        return {}
    if protocol_names is not None:
        from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
            protocol_class_name_for,
        )

        wanted = {cls for p in protocol_names if (cls := protocol_class_name_for(p))}
        protocols = [p for p in protocols if protocol_class_name_for(p) in wanted]
    amps: dict[str, dict[str, Any]] = {}
    for protocol_name in protocols:
        shape = ecode_class_for(protocol_name)
        try:
            traces = inspect_nwb(nwb_path, protocol_names=[protocol_name])["traces"]
        except (OSError, NWBInspectionError):
            continue
        values, skipped = _inspected_trace_amplitudes(traces, shape, round_decimals)
        if skipped:
            L.info(
                "Skipped %d non-current-clamp sweeps of %s in %s", skipped, protocol_name, nwb_path
            )
        amps[protocol_name] = values
    return amps


def _trace_dt_ms(trace: Mapping[str, Any]) -> float | None:
    """Sampling interval (ms) of a bluepyefe reader trace, or ``None`` if unknown."""
    from bluepyefe.tools import to_ms  # ruff: ignore[import-outside-top-level]

    dt, unit = trace.get("dt"), trace.get("t_unit")
    if not dt or not unit:
        return None
    try:
        return float(to_ms(float(dt), _unit_str(unit)))
    except (TypeError, ValueError):
        return None


def _inspected_trace_amplitudes(
    traces: list[dict], shape: str | None, round_decimals: int
) -> tuple[dict[str, Any], int]:
    """Amplitudes and timing of bluepyefe reader traces, and how many are not current clamp."""
    from bluepyefe.tools import to_nA  # ruff: ignore[import-outside-top-level]

    matchable: set[float] = set()
    secondary: set[float] = set()
    timing: dict[str, list[float]] = {}
    skipped = 0
    for t in traces:
        unit = _unit_str(t.get("i_unit"))
        if not is_current_clamp_stimulus(None, unit):
            # Covers units to_nA does not know: they are not current units.
            skipped += 1
            continue
        current_na = to_nA(np.asarray(t["current"], dtype=float), unit)
        dt_ms = _trace_dt_ms(t)
        match, second = estimate_matchable_amplitude(current_na, shape, dt_ms)
        if match is not None:
            matchable.add(round(match, round_decimals))
        if second is not None:
            secondary.add(round(second, round_decimals))
        _add_sweep_timing(timing, current_na, dt_ms, shape)
    values = {
        "matchable": sorted(matchable),
        "secondary": sorted(secondary),
        "timing": {key: distinct_times(times) for key, times in timing.items()},
    }
    return values, skipped


def _series_dt_ms(series: h5py.Group) -> float | None:
    """Sampling interval (ms) of an NWB series, from its ``starting_time`` rate (Hz)."""
    starting_time = series.get("starting_time")
    rate = starting_time.attrs.get("rate") if starting_time is not None else None
    return 1000.0 / float(rate) if rate else None


def _accumulate_trace_amplitudes(
    buckets: dict[str, Any],
    trace_names: list[str],
    stim_pres: h5py.Group,
    acquisition: h5py.Group | None,
    shape: str | None,
    round_decimals: int,
) -> int:
    """Estimate matchable/secondary amplitudes and timing of each trace, add to buckets.

    The sampling interval is the stimulus series' own, as bluepyefe's BBP reader
    takes it. Returns the number of stimulus series skipped as not current clamp.
    """
    from bluepyefe.tools import to_nA  # ruff: ignore[import-outside-top-level]

    skipped = 0
    for trace_name in trace_names:
        key_current = stim_key_for_trace(trace_name)
        if key_current is None or key_current not in stim_pres:
            continue
        data = stim_pres[key_current]["data"]
        voltage = acquisition.get(trace_name) if acquisition else None
        voltage_attrs = (
            voltage["data"].attrs if isinstance(voltage, h5py.Group) and "data" in voltage else None
        )
        conversion, unit = bbp_current_conversion(data.attrs, voltage_attrs)
        if not is_current_clamp_stimulus(stim_pres[key_current].attrs.get("neurodata_type"), unit):
            skipped += 1
            continue
        current = np.asarray(data[()], dtype=float) * conversion
        try:
            current_na = to_nA(current, unit)
        except Exception:  # ruff: ignore[blind-except]
            L.warning(
                "Skipping stimulus %s: unknown current unit %r",
                key_current,
                unit,
            )
            continue
        dt_ms = _series_dt_ms(stim_pres[key_current])
        match, second = estimate_matchable_amplitude(current_na, shape, dt_ms)
        if match is not None:
            buckets["matchable"].add(round(match, round_decimals))
        if second is not None:
            buckets["secondary"].add(round(second, round_decimals))
        _add_sweep_timing(buckets["timing"], current_na, dt_ms, shape)
    return skipped


def read_recording_amplitudes(
    nwb_path: Path,
    protocol_names: list[str],
    *,
    round_decimals: int = 3,
) -> dict[str, dict[str, Any]]:
    """Per-protocol amplitudes and timing, as ``{name: {"matchable", "secondary", "timing"}}``.

    ``timing`` maps each detected timing key to its distinct values in ms (see
    :func:`detect_stimulus_timing` and :func:`distinct_times`).

    Inspects every sweep under each ``data_organization/<cell>/<protocol>``
    group (BBP layout), reads its sibling current trace from
    ``stimulus/presentation``, converts it to nA with
    :func:`bluepyefe.tools.to_nA` (using the series' ``unit`` attr, default A,
    with bluepyefe's volts/volts mixup repair via :func:`bbp_current_conversion`),
    and estimates the amplitudes with :func:`estimate_matchable_amplitude`
    driven by each protocol's eCode shape — so the values correspond to what
    bluepyefe's ``in_target`` compares (the short middle step for the sAHP
    family, the first step for HyperDePol/DeHyperPol, the peak for
    ramp/cheops/…). Values are rounded to ``round_decimals`` decimal places
    (default 3 → 1 pA) and deduped. Stimulus series that are not current clamp
    (see :func:`is_current_clamp_stimulus`) are skipped.

    Files without the BBP ``data_organization`` layout are handled by
    :func:`read_amplitudes_via_inspection`, which reports amplitudes keyed by
    the protocol names bluepyefe's readers use, limited to the requested
    protocol classes.
    """
    requested = set(protocol_names)
    amps: dict[str, dict[str, Any]] = {
        p: {"matchable": set(), "secondary": set(), "timing": {}} for p in protocol_names
    }
    with h5py.File(str(nwb_path), "r") as f:
        if "data_organization" not in f or "stimulus" not in f:
            return read_amplitudes_via_inspection(
                nwb_path, protocol_names, round_decimals=round_decimals
            )
        stim_pres = f["stimulus"]["presentation"]
        acquisition = f.get("acquisition")
        for cell_id in f["data_organization"]:
            cell = f["data_organization"][cell_id]
            for protocol_name in cell:
                if protocol_name not in requested:
                    continue
                shape = ecode_class_for(protocol_name)
                skipped = 0
                for rep in cell[protocol_name]:
                    for sweep in cell[protocol_name][rep]:
                        skipped += _accumulate_trace_amplitudes(
                            amps[protocol_name],
                            list(cell[protocol_name][rep][sweep]),
                            stim_pres,
                            acquisition,
                            shape,
                            round_decimals,
                        )
                if skipped:
                    L.info(
                        "Skipped %d non-current-clamp stimuli of %s in %s",
                        skipped,
                        protocol_name,
                        nwb_path,
                    )
    return {
        p: {
            "matchable": sorted(d["matchable"]),
            "secondary": sorted(d["secondary"]),
            "timing": {key: distinct_times(times) for key, times in d["timing"].items()},
        }
        for p, d in amps.items()
    }


def read_amplitudes_from_nwb(
    nwb_path: Path,
    protocol_names: list[str],
    *,
    round_decimals: int = 3,
) -> dict[str, list[float]]:
    """Return ``{protocol_name: [matchable_amplitude_nA, ...]}``.

    Backward-compatible projection of :func:`read_recording_amplitudes` keeping
    only the *matchable* amplitude — the one bluepyefe's ``in_target`` compares
    (the short middle step for the sAHP family, the first step for
    HyperDePol/DeHyperPol, the peak for ramp/cheops/…, the step level for
    ``Step``).
    """
    return {
        name: values["matchable"]
        for name, values in read_recording_amplitudes(
            nwb_path, protocol_names, round_decimals=round_decimals
        ).items()
    }


# ---------------------------------------------------------------------------
# Stimulus timing
# ---------------------------------------------------------------------------

# Timing keys bluepyefe reads from a files-metadata entry, per eCode whose timing is
# detected here. The other eCodes (cheops, sineSpec, pinkNoise, capCheck, SpikeRec)
# are left to bluepyefe's own handling.
TIMING_KEYS: dict[str, tuple[str, ...]] = {
    "Step": ("ton", "toff"),
    "SAHP": ("ton", "tmid", "tmid2", "toff"),
    "HyperDePol": ("ton", "tmid", "toff"),
    "DeHyperPol": ("ton", "tmid", "toff"),
    # bluepyefe needs the onset of a ramp and takes its end at the current maximum.
    "Ramp": ("ton",),
}

# Width (ms) of the means compared on either side of a sample to find a step edge.
_EDGE_WINDOW_MS = 5.0
# An edge is a change of the windowed mean above this many noise standard deviations.
_EDGE_SNR = 8.0
# Percentiles of the sample-to-sample differences kept for the noise estimate.
_NOISE_PERCENTILES = (1.0, 99.0)
# Detected times closer than this (ms) are one value (sample jitter between sweeps).
_TIMING_CLUSTER_MS = 2.0
_TIMING_DECIMALS = 2
# Fractions of a ramp's rise between which it is fitted to extrapolate its onset: the start
# of the rise, since recorded ramps can bend.
_RAMP_FIT_RANGE = (0.05, 0.2)
_MIN_RAMP_FIT_SAMPLES = 3


def _noise_std(current: np.ndarray) -> float:
    """Noise standard deviation of a current trace, insensitive to its steps.

    Estimated from the sample-to-sample differences with their extreme percentiles
    left out, so the few large differences at step edges do not count. bluepyefe
    instead takes the first and last 50 samples, which overlap the stimulus when the
    rest before it is short (e.g. 20 ms at 0.5 ms sampling).
    """
    diff = np.diff(current)
    low, high = np.percentile(diff, _NOISE_PERCENTILES)
    return float(np.std(diff[(diff >= low) & (diff <= high)])) / math.sqrt(2)


def _edges(current: np.ndarray, half: int, threshold: float) -> list[int]:
    """Sample indices where the mean over ``half`` samples changes by more than ``threshold``.

    Each run of samples above the threshold is one edge, at its largest change; edges
    closer than two windows are one.
    """
    cumulative = np.concatenate(([0.0], np.cumsum(current)))
    index = np.arange(half, len(current) - half + 1)
    after = (cumulative[index + half] - cumulative[index]) / half
    before = (cumulative[index] - cumulative[index - half]) / half
    strength = after - before
    edges: list[int] = []
    above = np.flatnonzero(np.abs(strength) > threshold)
    for run in np.split(above, np.flatnonzero(np.diff(above) > 1) + 1):
        if not run.size:
            continue
        edge = int(index[run[np.argmax(np.abs(strength[run]))]])
        if not edges or edge - edges[-1] >= 2 * half:
            edges.append(edge)
    return edges


def _plateaus(current: np.ndarray, dt_ms: float) -> tuple[list[tuple[int, int, float]], float]:
    """Return the non-rest plateaus ``(start, end, level)`` of a trace, and the threshold.

    An edge is where the mean of the next ``_EDGE_WINDOW_MS`` differs from the mean of
    the previous ``_EDGE_WINDOW_MS`` by more than the threshold (``_EDGE_SNR`` noise
    standard deviations of that difference), placed at the largest difference. Each
    plateau's level is the median between two edges, relative to the first plateau
    (the rest before the stimulus); plateaus at the rest level are left out. Indices
    are samples; ``end`` is exclusive.
    """
    n = len(current)
    half = max(2, round(_EDGE_WINDOW_MS / dt_ms))
    if n < 4 * half:
        return [], 0.0
    threshold = max(
        _EDGE_SNR * _noise_std(current) * math.sqrt(2 / half), _ONSET_THRESHOLD_FLOOR_NA
    )
    bounds = [0, *_edges(current, half, threshold), n]
    levels = []
    for start, end in itertools.pairwise(bounds):
        margin = min(half, (end - start) // 4)
        levels.append((start, end, float(np.median(current[start + margin : end - margin]))))
    rest = levels[0][2]
    plateaus = [
        (start, end, level - rest)
        for start, end, level in levels[1:]
        if abs(level - rest) > threshold / 2
    ]
    return plateaus, threshold


def _ramp_onset_ms(current: np.ndarray, dt_ms: float) -> float | None:
    """Onset (ms) of a ramp: its rise, fitted with a line, extrapolated to the rest level."""
    half = max(2, round(_EDGE_WINDOW_MS / dt_ms))
    if len(current) < 4 * half:
        return None
    smooth = median_filter(current, size=_ONSET_SMOOTH_WIDTH)
    rest = float(np.median(current[:half]))
    peak = int(np.argmax(smooth))
    rise = float(smooth[peak]) - rest
    if rise <= _EDGE_SNR * _noise_std(current):
        return None
    low, high = (rest + fraction * rise for fraction in _RAMP_FIT_RANGE)
    start = int(np.argmax(smooth[:peak] > low))
    end = int(np.argmax(smooth[:peak] > high))
    if end - start < _MIN_RAMP_FIT_SAMPLES:
        return None
    slope, intercept = np.polyfit(np.arange(start, end), current[start:end], 1)
    onset = (rest - intercept) / slope
    if not 0 < onset < start:
        return None
    return float(onset) * dt_ms


def detect_stimulus_timing(
    current: np.ndarray, dt_ms: float, ecode_class: str | None
) -> dict[str, float] | None:
    """Detect the stimulus timing (ms) of one sweep, keyed as bluepyefe reads it.

    Returns the :data:`TIMING_KEYS` of ``ecode_class``, or ``None`` when that eCode's
    timing is not detected here, or the sweep does not have the expected shape: one
    plateau for ``Step``; three contiguous ones for ``SAHP`` (long, short, long); two
    contiguous ones for ``HyperDePol``/``DeHyperPol``. A sweep with no step (e.g. at
    0 nA) has no timing. ``ton`` of a ``Ramp`` is extrapolated from its rise.
    """
    keys = TIMING_KEYS.get(ecode_class or "")
    if keys is None or dt_ms <= 0:
        return None
    current = np.asarray(current, dtype=float)
    if ecode_class == "Ramp":
        onset = _ramp_onset_ms(current, dt_ms)
        return None if onset is None else {"ton": onset}

    plateaus, _ = _plateaus(current, dt_ms)
    if len(plateaus) != len(keys) - 1 or any(
        previous[1] != following[0] for previous, following in itertools.pairwise(plateaus)
    ):
        return None
    # Each plateau starts where the previous one ends: the times are every start and
    # the last end.
    times = [start for start, _, _ in plateaus] + [plateaus[-1][1]]
    return {key: index * dt_ms for key, index in zip(keys, times, strict=True)}


def distinct_times(values: list[float]) -> list[float]:
    """Distinct times (ms) among per-sweep values, sorted.

    Values within ``_TIMING_CLUSTER_MS`` of each other (sample jitter between
    sweeps) count once, as their median, rounded to 0.01 ms.
    """
    groups: list[list[float]] = []
    for value in sorted(values):
        if groups and value - groups[-1][-1] <= _TIMING_CLUSTER_MS:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [round(float(np.median(group)), _TIMING_DECIMALS) for group in groups]


def _add_sweep_timing(
    timing: dict[str, list[float]], current_na: np.ndarray, dt_ms: float | None, shape: str | None
) -> None:
    """Append one sweep's detected timing to ``timing`` (``{key: [ms, ...]}``)."""
    if dt_ms is None:
        return
    detected = detect_stimulus_timing(current_na, dt_ms, shape)
    for key, value in (detected or {}).items():
        timing.setdefault(key, []).append(value)

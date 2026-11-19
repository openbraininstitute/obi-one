"""Summary of the current-clamp stimuli of an ``ElectricalCellRecording``.

:class:`RecordingSummary` is the versioned JSON stored as the recording's
``recording_summary`` asset (one ``application/json`` file). entitycore does not
validate it: this module owns the format, documented in
``docs/recording-summary.md``. It is computed once from the NWB file — at ingest,
in a backfill, on request, or by the e-feature extraction task for a recording that
has none — so that nothing before extraction needs to read the NWB file.

Protocols are keyed by the *raw* names found in the file (not the ``Protocol``
subclass names); callers map them with ``protocol_class_name_for`` when reading,
so the mapping is not frozen at write time.

Amplitude and timing keys follow the names bluepyefe writes to
``extracted_features.json`` and reads from its files metadata: ``amp`` is always the
amplitude extraction targets are matched on, ``long_amp`` the long step of the sAHP
family and ``amp2`` the second step of HyperDePol/DeHyperPol; ``ton``, ``tmid``,
``tmid2`` and ``toff`` are the stimulus times.
"""

import logging
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from obi_one.scientific.library.electrical_cell_recording_properties import (
    TIMING_KEYS,
    ecode_class_for,
    read_protocols_from_nwb,
    read_recording_amplitudes,
)

L = logging.getLogger(__name__)

RECORDING_SUMMARY_FILE_NAME = "recording_summary.json"

# eFEL settings of the stored rheobases: the e-feature extraction defaults.
RHEOBASE_EFEL_SETTINGS: dict[str, float | bool] = {"Threshold": -20.0, "strict_stiminterval": True}

# Key of the second step, per eCode with one.
_SECOND_STEP_KEYS = {"SAHP": "long_amp", "HyperDePol": "amp2", "DeHyperPol": "amp2"}

# Step-shaped protocols recorded without a current step: their sweeps can only show
# spontaneous firing at the holding current, never a rheobase.
_NO_STEP_PROTOCOL_CLASSES = frozenset(
    {"SpontaneousProtocol", "SpontAPsProtocol", "StartHoldProtocol", "StartNoHoldProtocol"}
)

# How far (nA) a sweep bluepyefe reads may be from every stored amplitude before the
# summary is reported as inconsistent: the extraction task's absolute tolerance.
_AMPLITUDE_CHECK_TOLERANCE = 0.01
_AMPLITUDE_DECIMALS = 3


def _exclude_none(value: object) -> bool:
    return value is None


def _times_field(description: str) -> Any:
    return Field(default=None, min_length=1, exclude_if=_exclude_none, description=description)


class Units(BaseModel):
    """Units of the values in a :class:`RecordingSummary`."""

    model_config = ConfigDict(extra="forbid")

    current: Literal["nA"] = "nA"
    time: Literal["ms"] = "ms"


class ProtocolSummary(BaseModel):
    """Distinct amplitudes and stimulus times of one protocol, across its sweeps.

    Amplitudes are in nA relative to the holding current, sorted and rounded to
    0.001 nA; times are in ms from the start of the sweep. The lists are not paired
    sweep by sweep. A timing key is present when it was detected on at least one
    sweep; it has several values when the protocol's sweeps differ.
    """

    model_config = ConfigDict(extra="forbid")

    amp: list[float] = Field(min_length=1)
    """The amplitude extraction targets are matched on: the step level for
    ``Step``, the short middle step for the sAHP family, the first step for
    HyperDePol/DeHyperPol, the peak for ramp/posCheops/sineSpec, the trough for
    negCheops and the largest deviation for pinkNoise/capCheck."""

    amp2: list[float] | None = Field(default=None, exclude_if=_exclude_none)
    """HyperDePol/DeHyperPol only: the second step."""

    long_amp: list[float] | None = Field(default=None, exclude_if=_exclude_none)
    """sAHP family only: the long step around the short one."""

    ton: list[float] | None = _times_field("Stimulus onset.")
    tmid: list[float] | None = _times_field("Start of the second step (two-step eCodes).")
    tmid2: list[float] | None = _times_field("End of the short middle step (sAHP family).")
    toff: list[float] | None = _times_field("Stimulus end (not stored for ramps).")

    def timing(self) -> dict[str, list[float]]:
        """The stored timing keys with their values."""
        return {
            key: values
            for key in ("ton", "tmid", "tmid2", "toff")
            if (values := getattr(self, key)) is not None
        }

    def single_timing(self) -> dict[str, float] | None:
        """Timing to give bluepyefe for this protocol, one value per key.

        ``{}`` when no timing is stored, and ``None`` when a key has several values
        (the sweeps differ): bluepyefe takes one timing per protocol and file, so it
        must then detect the timing itself.
        """
        timing = self.timing()
        if any(len(values) != 1 for values in timing.values()):
            return None
        return {key: values[0] for key, values in timing.items()}


class RecordingSummary(BaseModel):
    """Versioned summary of one recording's current-clamp stimuli.

    Attributes:
        protocols: raw file protocol name -> :class:`ProtocolSummary`.
        rheobase: raw file protocol name -> rheobase (nA) of that protocol's sweeps
            alone, for each step protocol: the smallest amplitude whose sweep fires at
            least one spike (bluepyefe ``absolute`` strategy, read with the stored
            timing). ``None`` when no sweep fires; ``<= 0`` when a sweep fires
            without current injected (bluepyefe then cannot use the cell).
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    units: Units = Field(default_factory=Units)
    protocols: dict[str, ProtocolSummary] = Field(default_factory=dict)
    rheobase: dict[str, float | None] = Field(default_factory=dict)

    def rheobase_for(self, protocol_classes: Collection[str]) -> float | None:
        """The cell's rheobase (nA) when computed from the sweeps of ``protocol_classes``.

        ``protocol_classes`` are ``Protocol`` subclass names (e.g.
        ``"IDThreshProtocol"``). Like bluepyefe's ``absolute`` strategy over several
        protocols, this is the smallest of their rheobases. ``None`` when none of them
        fires, or when that smallest one is not positive: bluepyefe then drops the
        cell from relative extraction.
        """
        values = [
            value
            for raw_name, value in self.rheobase.items()
            if value is not None and _class_name(raw_name) in protocol_classes
        ]
        if not values or min(values) <= 0:
            return None
        return min(values)


def _class_name(raw_name: str) -> str | None:
    from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
        protocol_class_name_for,
    )

    return protocol_class_name_for(raw_name)


def relative_amplitudes_by_class(
    summaries: Mapping[str, RecordingSummary | None],
    rheobase_protocols: Collection[str],
    *,
    round_decimals: int = 1,
) -> dict[str, list[float]]:
    """Return ``{protocol_class_name: [% of rheobase, ...]}`` unioned across recordings.

    Each recording's amplitudes are divided by that recording's own rheobase from
    ``rheobase_protocols`` (``Protocol`` subclass names, see
    :meth:`RecordingSummary.rheobase_for`), so a value is offered when at least one
    recording has a sweep there. Recordings without a summary or a usable rheobase
    are skipped. Values are rounded to ``round_decimals`` decimal places (default 1
    → 0.1%).
    """
    combined: dict[str, set[float]] = {}
    for summary in summaries.values():
        rheobase = summary.rheobase_for(rheobase_protocols) if summary else None
        if summary is None or rheobase is None:
            continue
        for raw_name, protocol in summary.protocols.items():
            class_name = _class_name(raw_name)
            if class_name is None:
                continue
            combined.setdefault(class_name, set()).update(
                round(100.0 * amplitude / rheobase, round_decimals) for amplitude in protocol.amp
            )
    return {name: sorted(values) for name, values in combined.items()}


def rheobase_protocol_classes(summaries: Mapping[str, RecordingSummary | None]) -> list[str]:
    """``Protocol`` subclass names with a positive rheobase in at least one recording."""
    return sorted(
        {
            class_name
            for summary in summaries.values()
            if summary is not None
            for raw_name, value in summary.rheobase.items()
            if value is not None and value > 0 and (class_name := _class_name(raw_name))
        }
    )


def timing_by_class(
    summaries: Mapping[str, RecordingSummary | None],
) -> dict[str, dict[str, list[float]]]:
    """Return ``{protocol_class_name: {timing_key: [ms, ...]}}`` unioned across recordings."""
    combined: dict[str, dict[str, set[float]]] = {}
    for summary in summaries.values():
        if summary is None:
            continue
        for raw_name, protocol in summary.protocols.items():
            class_name = _class_name(raw_name)
            if class_name is None:
                continue
            for key, values in protocol.timing().items():
                combined.setdefault(class_name, {}).setdefault(key, set()).update(values)
    return {
        name: {key: sorted(values) for key, values in timing.items()}
        for name, timing in combined.items()
    }


def gives_rheobase(protocol_class: type) -> bool:
    """Whether a ``Protocol`` subclass's sweeps can give a rheobase.

    True for the ``Step`` eCode (the only one bluepyefe counts spikes for), except the
    protocols recorded without a current step (spontaneous and hold protocols).
    """
    return (
        getattr(protocol_class, "ecode_class", None) == "Step"
        and protocol_class.__name__ not in _NO_STEP_PROTOCOL_CLASSES
    )


def step_protocols(protocol_names: Collection[str]) -> list[str]:
    """The step protocols among ``protocol_names`` that have a rheobase, sorted.

    These are the protocols whose ``Protocol`` class :func:`gives_rheobase`.
    """
    from obi_one.scientific.tasks.emodel_building.task1_efeature_extraction.protocols_and_features.protocols import (  # ruff: ignore[line-too-long, import-outside-top-level]
        protocol_class_for,
    )

    selected = []
    for name in sorted(protocol_names):
        cls = protocol_class_for(name)
        if cls is not None and gives_rheobase(cls):
            selected.append(name)
    return selected


def _protocol_summary(name: str, values: Mapping) -> ProtocolSummary:
    ecode = ecode_class_for(name) or ""
    second_key = _SECOND_STEP_KEYS.get(ecode)
    second = {second_key: values["secondary"]} if second_key and values["secondary"] else {}
    keys = TIMING_KEYS.get(ecode, ())
    timing = {key: times for key, times in values.get("timing", {}).items() if key in keys}
    return ProtocolSummary(amp=values["matchable"], **second, **timing)


def _read_with_bluepyefe(
    nwb_path: Path,
    protocol_name: str,
    timing: Mapping[str, float],
    efel_settings: dict,
) -> list | None:
    """The bluepyefe recordings of one protocol, read as extraction does; ``None`` on error."""
    from bluepyefe.cell import Cell  # ruff: ignore[import-outside-top-level]

    cell = Cell(name=nwb_path.stem)
    entry = {"protocol_name": protocol_name, **timing, "filepath": str(nwb_path)}
    try:
        cell.read_recordings(
            protocol_data=[entry],
            protocol_name=protocol_name,
            recording_reader=None,
            efel_settings=efel_settings,
        )
    except Exception as e:  # ruff: ignore[blind-except]
        L.warning("bluepyefe could not read the %s sweeps of %s: %s", protocol_name, nwb_path, e)
        return None
    return cell.recordings


def _check_amplitudes(
    nwb_path: Path, protocol_name: str, amplitudes: list[float], recordings: list
) -> None:
    """Warn when a sweep bluepyefe reads matches none of the stored amplitudes.

    Uses bluepyefe's own target matching (``in_target`` in absolute mode, so the short
    step for the sAHP family) with the extraction task's absolute tolerance.
    """
    unmatched = [
        rec
        for rec in recordings
        if not any(
            rec.in_target(amplitude, _AMPLITUDE_CHECK_TOLERANCE, absolute_amplitude=True)
            for amplitude in amplitudes
        )
    ]
    if unmatched:
        matched_key = "amp2" if ecode_class_for(protocol_name) == "SAHP" else "amp"
        values = sorted(
            {round(float(getattr(rec, matched_key)), _AMPLITUDE_DECIMALS) for rec in unmatched}
        )
        L.warning(
            "bluepyefe reads %d %s sweeps of %s at %s nA, not among the summary's amplitudes"
            " %s: check the detected timing",
            len(unmatched),
            protocol_name,
            nwb_path,
            values,
            amplitudes,
        )


def _absolute_rheobase(recordings: list, protocol_name: str) -> float | None:
    """The ``absolute`` rheobase of bluepyefe ``recordings``, before bluepyefe drops a 0 nA one."""
    from bluepyefe.cell import Cell  # ruff: ignore[import-outside-top-level]
    from bluepyefe.rheobase import (  # ruff: ignore[import-outside-top-level]
        compute_rheobase_absolute,
    )

    cell = Cell(name=protocol_name)
    cell.recordings = recordings
    compute_rheobase_absolute(cell, [protocol_name])
    return None if cell.rheobase is None else round(float(cell.rheobase), _AMPLITUDE_DECIMALS)


def compute_recording_summary(
    nwb_path: Path,
    *,
    efel_settings: dict | None = None,
) -> RecordingSummary:
    """Compute the :class:`RecordingSummary` of a local NWB file.

    1. Amplitudes and stimulus timing of every current-clamp protocol in the file,
       detected per sweep (see ``read_recording_amplitudes``).
    2. Each protocol with a single timing is read once with bluepyefe using that
       timing, as extraction will read it, and a warning is logged for any sweep
       amplitude that is not among the stored ones.
    3. Each step protocol's rheobase is computed from those bluepyefe recordings
       (``absolute`` strategy, ``efel_settings``, default
       :data:`RHEOBASE_EFEL_SETTINGS`). A step protocol whose sweeps differ in timing
       is read without timing, as extraction then reads it.
    """
    protocol_names = read_protocols_from_nwb(nwb_path)
    protocols = {
        name: _protocol_summary(name, values)
        for name, values in read_recording_amplitudes(nwb_path, protocol_names).items()
        if values["matchable"]
    }
    settings = RHEOBASE_EFEL_SETTINGS if efel_settings is None else efel_settings
    steps = set(step_protocols(protocols))
    rheobase: dict[str, float | None] = {}
    for name, protocol in sorted(protocols.items()):
        timing = protocol.single_timing()
        if name not in steps and not timing:
            continue
        recordings = _read_with_bluepyefe(nwb_path, name, timing or {}, settings)
        if timing and recordings:
            _check_amplitudes(nwb_path, name, protocol.amp, recordings)
        if name in steps:
            rheobase[name] = _absolute_rheobase(recordings, name) if recordings else None
    return RecordingSummary(protocols=protocols, rheobase=rheobase)

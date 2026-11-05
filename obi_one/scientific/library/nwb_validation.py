"""Whether spikeinterface, and the spike sorting pipeline on it, can use an NWB file, or why not."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import BinaryIO

import h5py
import numpy as np
import spikeinterface.extractors as se
from pynwb import NWBHDF5IO

from obi_one.scientific.library.extracellular_recording_properties import (
    ELECTRODES_PATH,
    MIN_PREPROCESSING_DURATION,
    MIN_SAMPLING_FREQUENCY,
    electrical_series_paths,
    read_column,
    sampling_frequency,
)

MAX_QUOTED_ERROR = 300


@dataclass(frozen=True)
class NwbValidation:
    """What validating an NWB file found.

    Attributes:
        usable_series: Paths of the series the pipeline would process.
        skipped_series: Why the pipeline would pass over a series. In a file with errors, these
            are what would be left to fix after them.
        errors: Why the file cannot be used; a usable file has none.
        notes: What will affect a run of a usable file, without stopping it.
    """

    usable_series: tuple[str, ...] = ()
    skipped_series: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def message(self) -> str:
        """The outcome, for a person to read."""
        if self.errors:
            return "\n".join(["This NWB file cannot be used:", *self.errors, *self.skipped_series])
        usable = f"Usable series: {', '.join(self.usable_series)}."
        return "\n".join([usable, *self.skipped_series, *self.notes])


def shortened(error: Exception) -> str:
    """A library's error for a message: some quote whole parts of the file."""
    return f"{type(error).__name__}: {str(error)[:MAX_QUOTED_ERROR]}"


def timing_problems(series: h5py.Group, path: str) -> list[str]:
    if "starting_time" in series:
        rate = series["starting_time"].attrs.get("rate")
        if rate is None:
            return [f"{path}: its starting_time has no rate, so its sampling frequency is unknown."]
        return [f"{path}: its rate is {rate}, and must be positive."] if rate <= 0 else []
    if "timestamps" not in series:
        return [f"{path}: it has neither starting_time nor timestamps, so its timing is unknown."]
    if sampling_frequency(series) == 0:
        return [f"{path}: its timestamps do not increase, so they give no sampling frequency."]
    return []


def data_problems(series: h5py.Group, path: str) -> list[str]:
    if "data" not in series:
        return [f"{path}: it has no data."]
    data = series["data"]
    problems = [] if data.size else [f"{path}: its data is empty, with shape {data.shape}."]
    if "conversion" not in data.attrs:
        problems.append(f"{path}: its data has no conversion, so its traces cannot be scaled.")
    return problems


def channel_problems(series: h5py.Group, path: str, electrodes: h5py.Group) -> list[str]:
    if "electrodes" not in series:
        return [f"{path}: it has no electrodes, which link its channels to the electrodes table."]
    rows = series["electrodes"][()]
    num_rows = electrodes["id"].shape[0]
    if rows.size and (rows.min() < 0 or rows.max() >= num_rows):
        return [
            (
                f"{path}: its electrodes reach row {rows.max()}, but the electrodes table has only"
                f" {num_rows} rows."
            )
        ]
    problems = []
    data = series.get("data")
    num_channels = None
    if data is not None:
        num_channels = data.shape[1] if data.ndim > 1 else 1
        if rows.size != num_channels:
            problems.append(
                f"{path}: its data has {num_channels} channels, but its electrodes list"
                f" {rows.size}. Every channel of the data needs one row."
            )
    if "channel_conversion" in series and series["channel_conversion"].size != rows.size:
        problems.append(
            f"{path}: its channel_conversion has {series['channel_conversion'].size} values, but"
            f" it has {rows.size} channels."
        )
    names = read_column(electrodes, "channel_name")
    names = electrodes["id"][()] if names is None else names
    if len(set(names[rows].tolist())) < rows.size:
        problems.append(
            f"{path}: its channel names repeat. Spikeinterface identifies a channel by its"
            " channel_name, or its id without one, so they must differ within a series."
        )
    return problems


def geometry_problems(series: h5py.Group, path: str, electrodes: h5py.Group) -> list[str]:
    """What stops the file's probe geometry from being used, where it has one."""
    columns = set(electrodes.attrs.get("colnames", []))
    if not {"rel_x", "rel_y"} <= columns:
        return []
    groups = read_column(electrodes, "group_name")
    if groups is None:
        return [
            (
                f"{path}: the electrodes table has rel_x and rel_y but no group_name, which"
                " spikeinterface needs to make probes from them."
            )
        ]
    num_rows = electrodes["id"].shape[0]
    for column in ("rel_x", "rel_y"):
        if electrodes[column].shape[0] != num_rows:
            return [
                (
                    f"{path}: {column} has {electrodes[column].shape[0]} values, but the electrodes"
                    f" table has {num_rows} rows. Give positions only for the recorded channels."
                )
            ]
    rows = series["electrodes"][()]
    positions = np.column_stack(
        [electrodes["rel_x"][()].astype(float)[rows], electrodes["rel_y"][()].astype(float)[rows]]
    )
    if not np.isfinite(positions).all():
        missing = int((~np.isfinite(positions).all(axis=1)).sum())
        return [f"{path}: {missing} of its channels have no position in rel_x and rel_y."]
    for group in np.unique(groups[rows]):
        in_group = positions[groups[rows] == group]
        if len(np.unique(in_group, axis=0)) < len(in_group):
            return [
                (
                    f"{path}: some channels of group {group} share a position in rel_x and rel_y."
                    " Spikeinterface needs each contact of a probe to have its own."
                )
            ]
    return []


def why_skipped(
    series: h5py.Group, path: str, electrodes: h5py.Group, min_sampling_frequency: float
) -> str | None:
    """Why the pipeline would pass over a series spikeinterface can open, if it would."""
    rate = sampling_frequency(series)
    if rate < min_sampling_frequency:
        return (
            f"{path}: sampled at {rate:g} Hz, below {min_sampling_frequency:g} Hz, so it is taken"
            " to be LFP."
        )
    columns = set(electrodes.attrs.get("colnames", []))
    if {"rel_x", "rel_y"} <= columns:
        return None
    brain = " Its x, y and z columns are positions in the brain, not on the probe." * (
        "x" in columns
    )
    return (
        f"{path}: the electrodes table has no rel_x and rel_y, the positions of the contacts on"
        f" the probe, which spike sorting needs.{brain}"
    )


def unreadable_data_problem(series: h5py.Group, path: str) -> str | None:
    """Why the traces of a series cannot be read, found by reading one value."""
    data = series["data"]
    try:
        data[(0,) * data.ndim]
    except OSError as error:
        plist = data.id.get_create_plist()
        filters = [plist.get_filter(i) for i in range(plist.get_nfilters())]
        names = ", ".join(f"{name.decode() or 'unnamed'} ({code})" for code, _, _, name in filters)
        compressed = f" It is compressed with {names}, which may not be installed here." * bool(
            names
        )
        return f"{path}: its data cannot be read.{compressed} {shortened(error)}"
    return None


def run_notes(series: h5py.Group, path: str, electrodes: h5py.Group) -> list[str]:
    """What a run of a usable series should be expected to do, which depends on the form too."""
    notes = []
    duration = series["data"].shape[0] / sampling_frequency(series)
    if duration < MIN_PREPROCESSING_DURATION:
        notes.append(
            f"{path}: it lasts {duration:g} s. Preprocessing skips recordings shorter than its"
            f" Minimum duration field, {MIN_PREPROCESSING_DURATION:g} s by default, leaving only"
            " an error.txt, so lower that field to process it."
        )
    groups = read_column(electrodes, "group_name")
    num_groups = len(np.unique(groups[series["electrodes"][()]])) if groups is not None else 1
    if num_groups > 1:
        notes.append(
            f"{path}: its channels are in {num_groups} groups, so preprocessing makes"
            f" {num_groups} jobs from it, and each is sorted on its own."
        )
    return notes


def no_series_error(nwb: h5py.File) -> str:
    elsewhere = electrical_series_paths(nwb, root="processing")
    hint = f" Those at {', '.join(elsewhere)} are taken to be processed already." * bool(elsewhere)
    return f"It has no ElectricalSeries in acquisition, where raw traces belong.{hint}"


def validate_structure(nwb: h5py.File, min_sampling_frequency: float) -> NwbValidation:
    """What the file's own contents say, without asking spikeinterface to open it."""
    paths = electrical_series_paths(nwb)
    if not paths:
        return NwbValidation(errors=(no_series_error(nwb),))
    if ELECTRODES_PATH not in nwb:
        no_table = (
            f"It has no electrodes table at {ELECTRODES_PATH}, which names each channel and says"
            " where it sits on the probe."
        )
        return NwbValidation(errors=(no_table,))
    electrodes = nwb[ELECTRODES_PATH]
    errors: list[str] = []
    usable: list[str] = []
    skipped: list[str] = []
    notes: list[str] = []
    for path in paths:
        series = nwb[path]
        timing = timing_problems(series, path)
        # Geometry is read through the series' electrodes, so those must be sound first.
        channels = channel_problems(series, path, electrodes)
        problems = [
            *timing,
            *data_problems(series, path),
            *channels,
            *([] if channels else geometry_problems(series, path, electrodes)),
        ]
        errors += problems
        # Said of a series with errors too, so that fixing those doesn't only uncover this next.
        reason = None if timing else why_skipped(series, path, electrodes, min_sampling_frequency)
        if reason:
            skipped.append(reason)
        elif not problems:
            if problem := unreadable_data_problem(series, path):
                errors.append(problem)
            else:
                usable.append(path)
                notes += run_notes(series, path, electrodes)
    if not errors and not usable:
        errors.append("None of its ElectricalSeries can be used:")
    return NwbValidation(tuple(usable), tuple(skipped), tuple(errors), tuple(notes))


def library_errors(
    source: Path | str | BinaryIO, nwb: h5py.File, series_paths: tuple[str, ...]
) -> list[str]:
    """Anything the checks above missed, found by doing what the pipeline does with the file."""
    errors = []
    for path in series_paths:
        try:
            recording = (
                se.read_nwb_recording(file_path=source, electrical_series_path=path)
                if isinstance(source, Path | str)
                else se.read_nwb_recording(file=source, electrical_series_path=path)
            )
            recording.get_traces(start_frame=0, end_frame=1, return_in_uV=True)
        except Exception as error:  # ruff: ignore[blind-except]
            errors.append(f"{path}: spikeinterface could not read it. {shortened(error)}")
    try:
        NWBHDF5IO(file=nwb, mode="r", load_namespaces=True).read()
    except Exception as error:  # ruff: ignore[blind-except]
        errors.append(
            f"pynwb, which reads the probes' devices, could not read it. {shortened(error)}"
        )
    return errors


def validate_nwb_for_spikeinterface(
    source: Path | str | BinaryIO, *, min_sampling_frequency: float = MIN_SAMPLING_FREQUENCY
) -> NwbValidation:
    """Whether the spike sorting pipeline can read an NWB file, and if not, why not.

    Reads the file's metadata and one value of each usable series, so a remote file opened with
    ``HttpRangeFile`` costs little. It follows that it cannot say whether the traces hold spikes,
    or whether the scaling and probe positions are the right ones.

    Args:
        source: The file's path, or a file-like object.
        min_sampling_frequency: Series sampled below this are taken to be LFP and skipped.

    Raises:
        FileNotFoundError: If the path does not exist.
    """
    try:
        nwb = h5py.File(source, "r")
    except FileNotFoundError:
        raise
    except OSError as error:
        return NwbValidation(errors=(f"It is not an HDF5 NWB file: {error}",))
    with nwb:
        validation = validate_structure(nwb, min_sampling_frequency)
        if not validation.is_valid:
            return validation
        return replace(
            validation, errors=tuple(library_errors(source, nwb, validation.usable_series))
        )

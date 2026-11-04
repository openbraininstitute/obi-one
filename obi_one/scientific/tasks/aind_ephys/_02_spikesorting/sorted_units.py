"""A sort's units and spikes as SONATA files, the form the platform's spike viewer reads."""

import json
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import spikeinterface as si

CIRCUIT_CONFIG_FILE_NAME = "circuit_config.json"
NODES_FILE_NAME = "nodes.h5"
SPIKES_FILE_NAME = "spikes.h5"
RECORDINGS_FILE_NAME = "recordings.json"

ELECTRODE_PROPERTIES = ("brain_area", "electrode_name", "group")
MS_PER_S = 1000.0
NUM_AXES = 3


@dataclass
class SortedUnits:
    """One recording's units, one column value per unit, and their spikes in time order."""

    columns: dict[str, np.ndarray]
    node_ids: np.ndarray
    timestamps_ms: np.ndarray
    duration_ms: float
    channel_ids: np.ndarray
    electrode_positions: np.ndarray


def electrode_positions(recording: si.BaseRecording) -> np.ndarray:
    """Each channel's x, y, z: the electrode table's where it has them, else the probe's."""
    axes = [recording.get_property(axis) for axis in ("x", "y", "z")]
    if all(values is not None and np.issubdtype(values.dtype, np.number) for values in axes):
        positions = np.column_stack(axes)
        if np.isfinite(positions).all():
            return positions
    contacts = recording.get_channel_locations()
    return np.pad(contacts, ((0, 0), (0, NUM_AXES - contacts.shape[1])))


def template_amplitudes(
    sorting: si.BaseSorting, recording: si.BaseRecording
) -> tuple[np.ndarray, bool]:
    """Each unit's peak-to-peak template on each channel, and whether that is in microvolts."""
    analyzer = si.create_sorting_analyzer(sorting, recording, sparse=True)
    analyzer.compute(["random_spikes", "templates"])
    templates = analyzer.get_extension("templates").get_templates()
    return np.ptp(np.nan_to_num(templates), axis=1), analyzer.return_in_uV


def sorted_units(sorting: si.BaseSorting, recording: si.BaseRecording) -> SortedUnits:
    """Place each unit at the centre of its template's amplitude across the electrodes.

    ``sorting`` and ``recording`` have one segment, so the times run through the whole recording.
    """
    positions = electrode_positions(recording)
    num_units = len(sorting.unit_ids)
    amplitudes, in_uv = (
        template_amplitudes(sorting, recording)
        if num_units
        else (np.empty((0, recording.get_num_channels())), True)
    )
    totals = amplitudes.sum(axis=1, keepdims=True)
    # A unit with no spike far enough from the recording's ends has no template to place it by
    weights = np.where(totals > 0, amplitudes, 1.0)
    locations = weights @ positions / weights.sum(axis=1, keepdims=True)
    peaks = amplitudes.argmax(axis=1)

    columns = {
        "unit_id": np.asarray(sorting.unit_ids),
        "x": locations[:, 0],
        "y": locations[:, 1],
        "z": locations[:, 2],
        "peak_channel": np.asarray(recording.channel_ids)[peaks],
        "amplitude_uV" if in_uv else "amplitude": amplitudes[np.arange(num_units), peaks],
    }
    for key in ELECTRODE_PROPERTIES:
        values = recording.get_property(key)
        if values is not None:
            columns[key] = values[peaks]
    for key in sorting.get_property_keys():
        values = np.asarray(sorting.get_property(key))
        if values.ndim == 1:
            columns.setdefault(key, values)

    spikes = sorting.to_spike_vector()
    sampling_frequency = recording.get_sampling_frequency()
    return SortedUnits(
        columns=columns,
        node_ids=spikes["unit_index"].astype(np.uint64),  # ty:ignore[invalid-argument-type]
        timestamps_ms=spikes["sample_index"]  # ty:ignore[invalid-argument-type]
        / sampling_frequency
        * MS_PER_S,
        duration_ms=recording.get_num_samples() / sampling_frequency * MS_PER_S,
        channel_ids=np.asarray(recording.channel_ids),
        electrode_positions=positions,
    )


def _write_column(group: h5py.Group, name: str, values: np.ndarray) -> None:
    """A number per node, or SONATA's index into a library of the column's text values."""
    if values.dtype.kind in "iuf":
        group[name] = values
        return
    library, indices = np.unique(values.astype(str), return_inverse=True)
    group[name] = indices.astype(np.uint32)
    group.create_dataset(f"@library/{name}", data=library.astype(object), dtype=h5py.string_dtype())


def write_sorted_units(folder: Path, recordings: dict[str, SortedUnits]) -> None:
    """Write each recording's units as a node population and spike population of its name."""
    with h5py.File(folder / NODES_FILE_NAME, "w") as nodes:
        for name, units in recordings.items():
            population = nodes.create_group(f"nodes/{name}")
            num_units = len(units.columns["unit_id"])
            population["node_type_id"] = np.full(num_units, -1)
            population["node_group_id"] = np.zeros(num_units, dtype=np.uint32)
            population["node_group_index"] = np.arange(num_units, dtype=np.uint64)
            group = population.create_group("0")
            for column, values in units.columns.items():
                _write_column(group, column, values)

    with h5py.File(folder / SPIKES_FILE_NAME, "w") as spikes:
        for name, units in recordings.items():
            population = spikes.create_group(f"spikes/{name}")
            population.attrs["sorting"] = "by_time"
            population["node_ids"] = units.node_ids
            population["timestamps"] = units.timestamps_ms
            population["timestamps"].attrs["units"] = "ms"

    (folder / CIRCUIT_CONFIG_FILE_NAME).write_text(
        json.dumps(
            {
                "version": 2,
                "networks": {
                    "nodes": [
                        {
                            "nodes_file": NODES_FILE_NAME,
                            "populations": {name: {"type": "point_neuron"} for name in recordings},
                        }
                    ],
                    "edges": [],
                },
            },
            indent=2,
        )
    )
    (folder / RECORDINGS_FILE_NAME).write_text(
        json.dumps(
            {
                name: {
                    "duration_ms": units.duration_ms,
                    "channel_ids": units.channel_ids.astype(str).tolist(),
                    "electrode_positions": units.electrode_positions.tolist(),
                }
                for name, units in recordings.items()
            }
        )
    )

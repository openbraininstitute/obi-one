"""What an NWB file says about the channels of its extracellular recordings."""

import h5py
import numpy as np

ELECTRODES_PATH = "general/extracellular_ephys/electrodes"
# Series sampled below this are taken to be LFP, and are neither dispatched nor listed.
MIN_SAMPLING_FREQUENCY = 10_000.0
# Preprocessing skips recordings shorter than this, unless its form says otherwise.
MIN_PREPROCESSING_DURATION = 120.0
# As many timestamps as spikeinterface works out a sampling frequency from.
TIMESTAMPS_FOR_RATE = 1000


def channel_key(series_name: str, channel_id: object) -> str:
    """A channel's identity across an NWB file: several probes can name their channels alike."""
    text = channel_id.decode() if isinstance(channel_id, bytes) else str(channel_id)
    return f"{series_name}/{text}"


def sampling_frequency(series: h5py.Group) -> float:
    """A series' sampling frequency, from its rate or its timestamps; 0 if they do not increase."""
    if "starting_time" in series:
        return float(series["starting_time"].attrs["rate"])
    steps = np.diff(series["timestamps"][:TIMESTAMPS_FOR_RATE])
    step = float(np.median(steps)) if steps.size else 0.0
    return 1 / step if step > 0 else 0.0


def electrical_series_paths(nwb: h5py.File, root: str = "acquisition") -> list[str]:
    """The paths of the ElectricalSeries under a group, found as spikeinterface finds them."""
    found: list[str] = []

    def note(path: str, item: h5py.Group | h5py.Dataset) -> None:
        if isinstance(item, h5py.Group) and item.attrs.get("neurodata_type") == "ElectricalSeries":
            found.append(f"{root}/{path}")

    if root in nwb:
        nwb[root].visititems(note)
    return found


def read_column(electrodes: h5py.Group, name: str) -> np.ndarray | None:
    """A column of the electrodes table with its text decoded, if the table has it."""
    if name not in electrodes:
        return None
    column = electrodes[name]
    return column.asstr()[()] if h5py.check_string_dtype(column.dtype) else column[()]


def read_channel_options(
    nwb: h5py.File, min_sampling_frequency: float = MIN_SAMPLING_FREQUENCY
) -> list[dict[str, str]]:
    """Each raw channel of the file as an option for a form: its key, and what describes it.

    A channel is named as spikeinterface names it: by its ``channel_name``, or else by its ``id``.
    """
    electrodes = nwb[ELECTRODES_PATH]
    names = read_column(electrodes, "channel_name")
    if names is None:
        names = electrodes["id"][()]
    groups = read_column(electrodes, "group_name")
    locations = read_column(electrodes, "location")

    series = {
        path.rsplit("/", maxsplit=1)[-1]: nwb[path]
        for path in electrical_series_paths(nwb)
        if sampling_frequency(nwb[path]) >= min_sampling_frequency
    }
    options = []
    for series_name, item in series.items():
        for row in item["electrodes"][()]:
            description = [
                series_name if len(series) > 1 else None,
                str(names[row]),
                None if groups is None else str(groups[row]),
                None if locations is None else str(locations[row]),
            ]
            options.append(
                {
                    "value": channel_key(series_name, names[row]),
                    "label": " · ".join(part for part in description if part),
                }
            )
    return options

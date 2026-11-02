"""A synthetic ground-truth extracellular recording written as NWB, for tests and examples."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import spikeinterface as si
from neuroconv.tools.spikeinterface import add_recording_to_nwbfile
from pynwb import NWBHDF5IO, NWBFile
from pynwb.file import Subject

PROBE_NAME = "ToyProbe"
ELECTRICAL_SERIES_NAME = "ElectricalSeriesRaw"


def write_toy_nwb(
    path: Path,
    *,
    duration_s: float = 10.0,
    num_channels: int = 32,
    num_units: int = 10,
    seed: int = 2205,
) -> si.BaseSorting:
    """Write a toy recording to ``path`` as one probe's raw ElectricalSeries.

    The probe geometry goes into the electrodes table (``rel_x``/``rel_y``), which is where the
    dispatch stage reads it back from. Returns the ground-truth sorting.
    """
    recording, sorting = si.generate_ground_truth_recording(
        durations=[duration_s], num_channels=num_channels, num_units=num_units, seed=seed
    )
    locations = recording.get_channel_locations()
    recording.set_property("rel_x", locations[:, 0])
    recording.set_property("rel_y", locations[:, 1])
    recording.set_channel_groups(np.full(num_channels, PROBE_NAME, dtype=object))

    metadata = {
        "Ecephys": {
            "Device": [{"name": PROBE_NAME, "description": "Toy probe.", "manufacturer": "toy"}],
            "ElectrodeGroup": [
                {
                    "name": PROBE_NAME,
                    "description": "Toy probe channels.",
                    "location": "unknown",
                    "device": PROBE_NAME,
                }
            ],
            ELECTRICAL_SERIES_NAME: {
                "name": ELECTRICAL_SERIES_NAME,
                "description": "Toy ground-truth recording.",
            },
        }
    }
    nwbfile = NWBFile(  # ty:ignore[call-non-callable]
        session_description="Synthetic ground-truth extracellular recording.",
        identifier=str(uuid4()),
        session_start_time=datetime.now(UTC),
        subject=Subject(subject_id="toy", species="Mus musculus", sex="U", age="P90D"),
    )
    add_recording_to_nwbfile(
        recording, nwbfile=nwbfile, metadata=metadata, es_key=ELECTRICAL_SERIES_NAME
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with NWBHDF5IO(path, mode="w") as io:
        io.write(nwbfile)
    return sorting

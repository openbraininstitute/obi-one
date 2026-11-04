"""Tests for finding out why spikeinterface or the pipeline cannot use an NWB file."""

import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import h5py
import numpy as np
import pytest
import spikeinterface.extractors as se

from obi_one.scientific.library import nwb_validation
from obi_one.scientific.library.nwb_validation import validate_nwb_for_spikeinterface
from obi_one.scientific.tasks.aind_ephys.toy_recording import (
    ELECTRICAL_SERIES_NAME,
    write_toy_nwb,
)

ELECTRODES = "general/extracellular_ephys/electrodes"
SERIES = f"acquisition/{ELECTRICAL_SERIES_NAME}"
NUM_CHANNELS = 8
ZSTD_FILTER = 32015


@pytest.fixture(scope="module")
def base_nwb(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("nwb_validation") / "base.nwb"
    write_toy_nwb(path, duration_s=1.0, num_channels=NUM_CHANNELS, num_units=2)
    return path


def drop_column(nwb, name):
    del nwb[f"{ELECTRODES}/{name}"]
    table = nwb[ELECTRODES]
    table.attrs["colnames"] = [column for column in table.attrs["colnames"] if column != name]


def replace_dataset(nwb, path, values):
    attrs = dict(nwb[path].attrs)
    del nwb[path]
    nwb[path] = values
    for key, value in attrs.items():
        nwb[path].attrs[key] = value


def only_timestamps(nwb, timestamps=None):
    num_frames = nwb[f"{SERIES}/data"].shape[0]
    del nwb[f"{SERIES}/starting_time"]
    nwb[f"{SERIES}/timestamps"] = (
        np.arange(num_frames) / 30_000.0 if timestamps is None else timestamps
    )


def one_channel(nwb):
    replace_dataset(nwb, f"{SERIES}/data", nwb[f"{SERIES}/data"][:, 0])
    replace_dataset(nwb, f"{SERIES}/electrodes", nwb[f"{SERIES}/electrodes"][:1])


def move_to_processing(nwb):
    nwb.require_group("processing/ecephys")
    nwb.move(SERIES, f"processing/ecephys/{ELECTRICAL_SERIES_NAME}")


def same_positions(nwb):
    replace_dataset(nwb, f"{ELECTRODES}/rel_x", np.zeros(NUM_CHANNELS))
    replace_dataset(nwb, f"{ELECTRODES}/rel_y", np.zeros(NUM_CHANNELS))


def set_rate(rate):
    def change(nwb):
        nwb[f"{SERIES}/starting_time"].attrs["rate"] = rate

    return change


def needing_a_missing_filter(nwb):
    data = nwb[f"{SERIES}/data"]
    attrs = dict(data.attrs)
    values = data[:]
    del nwb[f"{SERIES}/data"]
    data = nwb.create_dataset(
        f"{SERIES}/data",
        shape=values.shape,
        dtype=values.dtype,
        chunks=(1000, NUM_CHANNELS),
        compression=ZSTD_FILTER,
        allow_unknown_filter=True,
    )
    data.id.write_direct_chunk((0, 0), values[:1000].tobytes(), filter_mask=0)
    for key, value in attrs.items():
        data.attrs[key] = value


NOT_USABLE = {
    "no acquisition": (lambda nwb: nwb.__delitem__("acquisition"), "no ElectricalSeries"),
    "another neurodata type": (
        lambda nwb: nwb[SERIES].attrs.__setitem__("neurodata_type", "TimeSeries"),
        "no ElectricalSeries",
    ),
    "only in processing": (move_to_processing, "processed already"),
    "no electrodes table": (lambda nwb: nwb.__delitem__(ELECTRODES), "no electrodes table"),
    "no electrodes in the series": (
        lambda nwb: nwb.__delitem__(f"{SERIES}/electrodes"),
        "it has no electrodes",
    ),
    "too few electrodes": (
        lambda nwb: replace_dataset(nwb, f"{SERIES}/electrodes", np.arange(4)),
        f"data has {NUM_CHANNELS} channels, but its electrodes list 4",
    ),
    "electrodes past the table": (
        lambda nwb: replace_dataset(nwb, f"{SERIES}/electrodes", np.arange(NUM_CHANNELS) + 100),
        "only 8 rows",
    ),
    "no timing": (
        lambda nwb: nwb.__delitem__(f"{SERIES}/starting_time"),
        "neither starting_time nor timestamps",
    ),
    "no rate": (
        lambda nwb: nwb[f"{SERIES}/starting_time"].attrs.__delitem__("rate"),
        "has no rate",
    ),
    "a zero rate": (set_rate(0.0), "must be positive"),
    "flat timestamps": (
        lambda nwb: only_timestamps(nwb, np.ones(nwb[f"{SERIES}/data"].shape[0])),
        "timestamps do not increase",
    ),
    "only lfp": (set_rate(2500.0), "taken to be LFP"),
    "no rel_x": (lambda nwb: drop_column(nwb, "rel_x"), "no rel_x and rel_y"),
    "no rel_y": (lambda nwb: drop_column(nwb, "rel_y"), "no rel_x and rel_y"),
    "no group_name": (lambda nwb: drop_column(nwb, "group_name"), "no group_name"),
    "no positions": (
        lambda nwb: replace_dataset(nwb, f"{ELECTRODES}/rel_x", np.full(NUM_CHANNELS, np.nan)),
        f"{NUM_CHANNELS} of its channels have no position",
    ),
    "shared positions": (same_positions, "share a position"),
    "repeated channel names": (
        lambda nwb: replace_dataset(
            nwb,
            f"{ELECTRODES}/channel_name",
            np.array(["same"] * NUM_CHANNELS, dtype=h5py.string_dtype()),
        ),
        "channel names repeat",
    ),
    "empty data": (
        lambda nwb: replace_dataset(
            nwb, f"{SERIES}/data", np.zeros((0, NUM_CHANNELS), dtype="int16")
        ),
        "data is empty",
    ),
    "a filter that is not installed": (needing_a_missing_filter, f"({ZSTD_FILTER})"),
    "no conversion": (
        lambda nwb: nwb[f"{SERIES}/data"].attrs.__delitem__("conversion"),
        "no conversion",
    ),
    "a short channel_conversion": (
        lambda nwb: nwb[SERIES].__setitem__("channel_conversion", np.ones(3)),
        "channel_conversion has 3 values",
    ),
    "something only pynwb minds": (
        lambda nwb: nwb.__delitem__("general/devices"),
        "pynwb",
    ),
}
# Spikeinterface raises on these as it opens the file, with messages far from their cause.
REFUSED_BY_SPIKEINTERFACE = (
    "no electrodes table",
    "no electrodes in the series",
    "electrodes past the table",
    "no timing",
    "no rate",
    "no group_name",
    "shared positions",
    "no conversion",
    "a short channel_conversion",
)
STILL_USABLE = {
    "unchanged": lambda _: None,
    "only timestamps": only_timestamps,
    "no channel names": lambda nwb: drop_column(nwb, "channel_name"),
    "one channel": one_channel,
}


@pytest.fixture
def broken(base_nwb, tmp_path):
    def make(change) -> Path:
        path = tmp_path / "broken.nwb"
        shutil.copy(base_nwb, path)
        with h5py.File(path, "r+") as nwb:
            change(nwb)
        return path

    return make


class TestValidateNwbForSpikeinterface:
    @pytest.mark.parametrize("case", NOT_USABLE)
    def test_it_says_why_a_file_cannot_be_used(self, broken, case):
        change, reason = NOT_USABLE[case]

        validation = validate_nwb_for_spikeinterface(broken(change))

        assert not validation.is_valid
        assert reason in validation.message

    @pytest.mark.parametrize("case", STILL_USABLE)
    def test_a_usable_file_passes(self, broken, case):
        validation = validate_nwb_for_spikeinterface(broken(STILL_USABLE[case]))

        assert validation.is_valid, validation.message
        assert validation.usable_series == (SERIES,)
        assert SERIES in validation.message

    @pytest.mark.parametrize("case", REFUSED_BY_SPIKEINTERFACE)
    def test_what_it_refuses_spikeinterface_really_refuses(self, broken, case):
        path = broken(NOT_USABLE[case][0])

        with pytest.raises(Exception):  # ruff: ignore[pytest-raises-too-broad, assert-raises-exception]
            se.read_nwb_recording(path, electrical_series_path=SERIES)

    def test_an_lfp_series_beside_a_raw_one_is_only_skipped(self, broken):
        def add_lfp(nwb):
            nwb.copy(SERIES, "acquisition/Lfp")
            lfp = nwb["acquisition/Lfp"]
            lfp["starting_time"].attrs["rate"] = 2500.0
            # A copy loses the reference to the table, and pynwb wants ids of its own.
            lfp["electrodes"].attrs["table"] = nwb[ELECTRODES].ref
            for item in (lfp, lfp["electrodes"]):
                item.attrs["object_id"] = str(uuid4())

        validation = validate_nwb_for_spikeinterface(broken(add_lfp))

        assert validation.is_valid, validation.message
        assert validation.usable_series == (SERIES,)
        assert "acquisition/Lfp" in validation.skipped_series[0]
        assert "taken to be LFP" in validation.message

    def test_a_bad_series_spoils_the_file_even_beside_a_good_one(self, broken):
        def add_bad_series(nwb):
            nwb.copy(SERIES, "acquisition/Bad")
            del nwb["acquisition/Bad/electrodes"]

        validation = validate_nwb_for_spikeinterface(broken(add_bad_series))

        assert not validation.is_valid
        assert "acquisition/Bad" in validation.message

    def test_one_fault_does_not_hide_another(self, broken):
        def two_faults(nwb):
            del nwb[f"{SERIES}/data"].attrs["conversion"]
            drop_column(nwb, "rel_x")

        message = validate_nwb_for_spikeinterface(broken(two_faults)).message

        assert "no conversion" in message
        assert "no rel_x and rel_y" in message

    def test_positions_for_every_contact_of_a_probe_are_refused(self, broken):
        def too_many(nwb):
            replace_dataset(nwb, f"{ELECTRODES}/rel_x", np.arange(960.0))

        message = validate_nwb_for_spikeinterface(broken(too_many)).message

        assert "rel_x has 960 values" in message

    def test_a_recording_preprocessing_would_skip_gets_a_note(self, base_nwb):
        validation = validate_nwb_for_spikeinterface(base_nwb)

        assert validation.is_valid
        assert "lasts 1 s" in validation.notes[0]
        assert "Minimum duration" in validation.message

    def test_a_long_enough_recording_gets_no_note(self, broken):
        def make_it_long(nwb):
            nwb[f"{SERIES}/starting_time"].attrs["rate"] = 10_000.0
            frames = nwb[f"{SERIES}/data"][:]
            replace_dataset(nwb, f"{SERIES}/data", np.tile(frames, (60, 1)))

        validation = validate_nwb_for_spikeinterface(broken(make_it_long))

        assert validation.is_valid, validation.message
        assert validation.notes == ()

    def test_several_groups_are_said_to_make_several_jobs(self, broken):
        def split_into_shanks(nwb):
            shanks = np.array(["a", "b"] * (NUM_CHANNELS // 2), dtype=h5py.string_dtype())
            replace_dataset(nwb, f"{ELECTRODES}/group_name", shanks)

        validation = validate_nwb_for_spikeinterface(broken(split_into_shanks))

        assert "2 groups" in validation.message
        assert "2 jobs" in validation.message

    def test_a_file_that_is_not_hdf5_is_said_to_be_so(self, tmp_path):
        path = tmp_path / "text.nwb"
        path.write_text("not hdf5")

        assert "not an HDF5" in validate_nwb_for_spikeinterface(path).message

    def test_a_missing_file_is_an_error_of_the_call(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            validate_nwb_for_spikeinterface(tmp_path / "missing.nwb")

    def test_a_file_like_object_can_be_validated(self, base_nwb):
        with base_nwb.open("rb") as file:
            validation = validate_nwb_for_spikeinterface(file)

        assert validation.is_valid, validation.message

    def test_what_only_spikeinterface_finds_is_reported(self, base_nwb):
        with patch.object(
            nwb_validation.se, "read_nwb_recording", side_effect=RuntimeError("surprise")
        ):
            validation = validate_nwb_for_spikeinterface(base_nwb)

        assert not validation.is_valid
        assert "spikeinterface could not read it" in validation.message
        assert "surprise" in validation.message

    def test_a_long_library_error_is_shortened(self, base_nwb):
        with patch.object(
            nwb_validation.se, "read_nwb_recording", side_effect=RuntimeError("x" * 5000)
        ):
            message = validate_nwb_for_spikeinterface(base_nwb).message

        assert len(message) < 600

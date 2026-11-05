"""Tests for reading the channels of an extracellular recording's NWB file."""

import h5py
import numpy as np
import pytest

from obi_one.scientific.library.extracellular_recording_properties import (
    ELECTRODES_PATH,
    channel_key,
    read_channel_options,
    sampling_frequency,
)

RAW_RATE = 30_000.0
LFP_RATE = 2_500.0


def add_series(nwb: h5py.File, name: str, rows: list[int], *, rate: float = RAW_RATE) -> None:
    series = nwb.create_group(f"acquisition/{name}")
    series.attrs["neurodata_type"] = "ElectricalSeries"
    series["electrodes"] = np.array(rows)
    series["starting_time"] = 0.0
    series["starting_time"].attrs["rate"] = rate


def add_electrodes(nwb: h5py.File, **columns: list) -> None:
    table = nwb.require_group(ELECTRODES_PATH)
    for name, values in columns.items():
        data = np.array(values, dtype=h5py.string_dtype()) if isinstance(values[0], str) else values
        table[name] = data


@pytest.fixture
def nwb(tmp_path):
    with h5py.File(tmp_path / "file.nwb", "w") as file:
        yield file


class TestChannelKey:
    @pytest.mark.parametrize("channel", ["AP1", b"AP1", np.str_("AP1")])
    def test_text_reads_alike_however_it_is_stored(self, channel):
        assert channel_key("Series", channel) == "Series/AP1"

    def test_numbers_read_as_they_do_in_the_table(self):
        assert channel_key("Series", np.int64(3)) == "Series/3"


class TestSamplingFrequency:
    def test_it_is_read_from_the_rate(self, nwb):
        add_series(nwb, "Raw", [0])

        assert sampling_frequency(nwb["acquisition/Raw"]) == RAW_RATE

    def test_it_is_worked_out_from_the_timestamps_otherwise(self, nwb):
        series = nwb.create_group("series")
        series["timestamps"] = np.array([1.0, 1.5, 2.0])

        assert sampling_frequency(series) == pytest.approx(2.0)

    def test_timestamps_that_do_not_increase_give_none(self, nwb):
        series = nwb.create_group("series")
        series["timestamps"] = np.array([1.0, 1.0, 1.0])

        assert sampling_frequency(series) == 0


class TestReadChannelOptions:
    def test_a_channel_is_named_by_its_channel_name_and_described(self, nwb):
        add_electrodes(
            nwb,
            id=[10, 11],
            channel_name=["AP0", "AP1"],
            group_name=["probeA", "probeA"],
            location=["CA1", "CA3"],
        )
        add_series(nwb, "Raw", [0, 1])

        assert read_channel_options(nwb) == [
            {"value": "Raw/AP0", "label": "AP0 · probeA · CA1"},
            {"value": "Raw/AP1", "label": "AP1 · probeA · CA3"},
        ]

    def test_a_table_without_channel_names_uses_the_ids(self, nwb):
        add_electrodes(nwb, id=[10, 11])
        add_series(nwb, "Raw", [0, 1])

        assert read_channel_options(nwb) == [
            {"value": "Raw/10", "label": "10"},
            {"value": "Raw/11", "label": "11"},
        ]

    def test_a_series_is_narrowed_to_its_electrodes_in_their_order(self, nwb):
        add_electrodes(nwb, id=[10, 11, 12])
        add_series(nwb, "Raw", [2, 0])

        assert [option["value"] for option in read_channel_options(nwb)] == ["Raw/12", "Raw/10"]

    def test_probes_naming_their_channels_alike_stay_apart(self, nwb):
        add_electrodes(nwb, id=[0, 1], channel_name=["AP0", "AP0"])
        add_series(nwb, "ProbeA", [0])
        add_series(nwb, "ProbeB", [1])

        assert read_channel_options(nwb) == [
            {"value": "ProbeA/AP0", "label": "ProbeA · AP0"},
            {"value": "ProbeB/AP0", "label": "ProbeB · AP0"},
        ]

    def test_lfp_series_are_left_out(self, nwb):
        add_electrodes(nwb, id=[0, 1])
        add_series(nwb, "Raw", [0])
        add_series(nwb, "Lfp", [1], rate=LFP_RATE)

        assert [option["value"] for option in read_channel_options(nwb)] == ["Raw/0"]

    def test_a_series_nested_in_the_acquisition_is_found(self, nwb):
        add_electrodes(nwb, id=[0])
        add_series(nwb, "Container/Raw", [0])

        assert [option["value"] for option in read_channel_options(nwb)] == ["Raw/0"]

    def test_other_acquisitions_are_left_out(self, nwb):
        add_electrodes(nwb, id=[0])
        add_series(nwb, "Raw", [0])
        nwb.create_group("acquisition/Behaviour").attrs["neurodata_type"] = "TimeSeries"

        assert [option["value"] for option in read_channel_options(nwb)] == ["Raw/0"]

    def test_a_file_without_electrodes_is_an_error(self, nwb):
        with pytest.raises(KeyError):
            read_channel_options(nwb)

"""A sort's units as the SONATA files the platform's spike viewer reads."""

import json
from unittest.mock import patch

import h5py
import numpy as np
import pytest
import spikeinterface as si

from obi_one.core.info import Info
from obi_one.scientific.tasks.aind_ephys._03_spikesorting import (
    sorted_units as sorted_units_module,
    task as sorting_task,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.sorted_units import (
    CIRCUIT_CONFIG_FILE_NAME,
    NODES_FILE_NAME,
    RECORDINGS_FILE_NAME,
    SPIKES_FILE_NAME,
    electrode_positions,
    sorted_units,
    write_sorted_units,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.spykingcircus2.config import (
    AINDEPhysSpikeSortingSpykingCircus2SingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.spykingcircus2.task import (
    AINDEPhysSpikeSortingSpykingCircus2Task,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.task import SORTER_LOG_FILE_NAME
from obi_one.scientific.tasks.aind_ephys.blocks import JobKwargs
from obi_one.scientific.tasks.aind_ephys.utils import dump_recording, write_skip

FS = 30000.0
NAME = "rec"


def two_channel_recording() -> si.BaseRecording:
    recording = si.generate_recording(durations=[1.0], num_channels=2, seed=0)
    recording.set_channel_locations(np.array([[0.0, 0.0], [0.0, 100.0]]))
    return recording


def two_units() -> si.BaseSorting:
    return si.NumpySorting.from_samples_and_labels(
        [np.array([300, 3000, 15000])],
        [np.array([0, 1, 0])],
        sampling_frequency=FS,
    )


def form_for(root, source):
    form = AINDEPhysSpikeSortingSpykingCircus2SingleConfig(
        info=Info(campaign_name="Test", campaign_description="Test."),
        initialize=AINDEPhysSpikeSortingSpykingCircus2SingleConfig.Initialize(
            preprocessing_output_path=source
        ),
        job_kwargs=JobKwargs(n_jobs=1),
    )
    form.coordinate_output_root = root
    return form


def preprocessed_folder(root, durations=(2.0,)):
    folder = root / "preprocessing"
    binary = si.generate_recording(durations=list(durations), num_channels=4, seed=0).save(
        folder=folder / f"preprocessed_{NAME}"
    )
    dump_recording(binary, folder, f"binary_{NAME}", relative_to=folder)
    return folder


def fake_run_sorter(_sorter_name, _recording, *, folder, **_params):
    folder_path = sorting_task.Path(folder)
    folder_path.mkdir(parents=True)
    (folder_path / SORTER_LOG_FILE_NAME).write_text("{}")
    return si.generate_sorting(num_units=2, durations=[2.0], sampling_frequency=FS, seed=0)


class TestElectrodePositions:
    def test_a_probes_contacts_lie_in_a_plane_at_zero(self):
        positions = electrode_positions(two_channel_recording())

        np.testing.assert_array_equal(positions, [[0, 0, 0], [0, 100, 0]])

    def test_the_electrode_tables_coordinates_come_first(self):
        recording = two_channel_recording()
        recording.set_property("x", np.array([1.0, 2.0]))
        recording.set_property("y", np.array([3.0, 4.0]))
        recording.set_property("z", np.array([5.0, 6.0]))

        np.testing.assert_array_equal(electrode_positions(recording), [[1, 3, 5], [2, 4, 6]])

    def test_unregistered_coordinates_fall_back_on_the_probe(self):
        recording = two_channel_recording()
        for axis in ("x", "y", "z"):
            recording.set_property(axis, np.array([np.nan, np.nan]))

        np.testing.assert_array_equal(electrode_positions(recording), [[0, 0, 0], [0, 100, 0]])


class TestSortedUnits:
    def test_a_unit_sits_at_the_centre_of_its_amplitude_across_the_electrodes(self):
        amplitudes = np.array([[10.0, 0.0], [10.0, 30.0]])
        with patch.object(
            sorted_units_module, "template_amplitudes", return_value=(amplitudes, True)
        ):
            units = sorted_units(two_units(), two_channel_recording())

        np.testing.assert_allclose(units.columns["y"], [0.0, 75.0])
        np.testing.assert_array_equal(units.columns["z"], [0.0, 0.0])
        np.testing.assert_array_equal(units.columns["amplitude_uV"], [10.0, 30.0])
        assert units.columns["peak_channel"].tolist() == [
            two_channel_recording().channel_ids[0],
            two_channel_recording().channel_ids[1],
        ]

    def test_a_unit_without_a_template_sits_in_the_middle_of_the_probe(self):
        amplitudes = np.array([[0.0, 0.0], [1.0, 0.0]])
        with patch.object(
            sorted_units_module, "template_amplitudes", return_value=(amplitudes, True)
        ):
            units = sorted_units(two_units(), two_channel_recording())

        assert units.columns["y"][0] == pytest.approx(50.0)

    def test_templates_of_a_real_recording_place_units_near_their_peak_electrode(self):
        recording, sorting = si.generate_ground_truth_recording(
            durations=[5.0], num_channels=16, num_units=4, seed=0
        )

        units = sorted_units(sorting, recording)

        channels = list(recording.channel_ids)
        peaks = units.electrode_positions[
            [channels.index(c) for c in units.columns["peak_channel"]]
        ]
        locations = np.column_stack([units.columns[axis] for axis in ("x", "y", "z")])
        assert (np.linalg.norm(locations - peaks, axis=1) < 75).all()

    def test_spikes_are_in_ms_and_units_are_indexed_by_row(self):
        with patch.object(
            sorted_units_module,
            "template_amplitudes",
            return_value=(np.ones((2, 2)), True),
        ):
            units = sorted_units(two_units(), two_channel_recording())

        np.testing.assert_allclose(units.timestamps_ms, [10.0, 100.0, 500.0])
        assert units.node_ids.tolist() == [0, 1, 0]
        assert units.duration_ms == pytest.approx(1000.0)

    def test_a_sort_with_no_units_is_an_empty_population(self):
        sorting = si.NumpySorting.from_unit_dict({}, sampling_frequency=FS)

        units = sorted_units(sorting, two_channel_recording())

        assert len(units.columns["x"]) == 0
        assert len(units.timestamps_ms) == 0

    def test_the_sorters_own_properties_are_kept(self):
        sorting = two_units()
        sorting.set_property("KSLabel", np.array(["good", "mua"]))
        with patch.object(
            sorted_units_module, "template_amplitudes", return_value=(np.ones((2, 2)), True)
        ):
            units = sorted_units(sorting, two_channel_recording())

        assert units.columns["KSLabel"].tolist() == ["good", "mua"]


class TestWriteSortedUnits:
    @pytest.fixture
    def folder(self, tmp_path):
        with patch.object(
            sorted_units_module,
            "template_amplitudes",
            return_value=(np.array([[10.0, 0.0], [0.0, 10.0]]), False),
        ):
            units = sorted_units(two_units(), two_channel_recording())
        units.columns["label"] = np.array(["good", "mua"])
        write_sorted_units(tmp_path, {NAME: units, "other": units})
        return tmp_path

    def test_each_recording_is_a_node_population(self, folder):
        config = json.loads((folder / CIRCUIT_CONFIG_FILE_NAME).read_text())
        (nodes_entry,) = config["networks"]["nodes"]

        assert nodes_entry["nodes_file"] == NODES_FILE_NAME
        assert set(nodes_entry["populations"]) == {NAME, "other"}

    def test_units_are_positioned_nodes(self, folder):
        with h5py.File(folder / NODES_FILE_NAME) as nodes:
            group = nodes[f"nodes/{NAME}/0"]
            assert group["y"][()].tolist() == [0.0, 100.0]
            assert len(nodes[f"nodes/{NAME}/node_type_id"]) == 2
            assert "amplitude" in group

    def test_text_columns_are_coded_by_a_library(self, folder):
        with h5py.File(folder / NODES_FILE_NAME) as nodes:
            group = nodes[f"nodes/{NAME}/0"]
            library = [value.decode() for value in group["@library/label"][()]]
            assert [library[index] for index in group["label"][()]] == ["good", "mua"]

    def test_spikes_are_a_sonata_report_in_ms(self, folder):
        with h5py.File(folder / SPIKES_FILE_NAME) as spikes:
            population = spikes[f"spikes/{NAME}"]
            assert population["node_ids"][()].tolist() == [0, 1, 0]
            assert population["timestamps"].attrs["units"] == "ms"
            np.testing.assert_allclose(population["timestamps"][()], [10.0, 100.0, 500.0])

    def test_each_recording_lists_its_span_and_electrodes(self, folder):
        recording = json.loads((folder / RECORDINGS_FILE_NAME).read_text())[NAME]

        assert recording["duration_ms"] == pytest.approx(1000.0)
        assert recording["electrode_positions"] == [[0.0, 0.0, 0.0], [0.0, 100.0, 0.0]]
        assert len(recording["channel_ids"]) == 2


class TestTheTaskWritesThem:
    def test_beside_the_sorting(self, tmp_path):
        form = form_for(tmp_path / "sorting", preprocessed_folder(tmp_path))

        with patch.object(sorting_task.ss, "run_sorter", side_effect=fake_run_sorter):
            folder = AINDEPhysSpikeSortingSpykingCircus2Task(config=form).execute()

        with h5py.File(folder / NODES_FILE_NAME) as nodes:
            assert len(nodes[f"nodes/{NAME}/0/x"]) == 2

    def test_segments_run_on_in_one_time(self, tmp_path):
        form = form_for(tmp_path / "sorting", preprocessed_folder(tmp_path, durations=(1.0, 1.0)))

        with patch.object(sorting_task.ss, "run_sorter", side_effect=fake_run_sorter):
            folder = AINDEPhysSpikeSortingSpykingCircus2Task(config=form).execute()

        with h5py.File(folder / SPIKES_FILE_NAME) as spikes:
            timestamps = spikes[f"spikes/{NAME}/timestamps"][()]
        assert (np.diff(timestamps) >= 0).all()
        assert timestamps[-1] > 1000.0

    def test_not_when_every_recording_was_skipped(self, tmp_path):
        write_skip(tmp_path / f"preprocessed_{NAME}", "Too short")
        form = form_for(tmp_path / "sorting", tmp_path)

        folder = AINDEPhysSpikeSortingSpykingCircus2Task(config=form).execute()

        assert not (folder / NODES_FILE_NAME).exists()
        assert not (folder / CIRCUIT_CONFIG_FILE_NAME).exists()

from unittest.mock import MagicMock

import h5py
import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.stimuli.spike.time_distribution import (
    SpikeTimeDistributionSpikeStimulus,
)
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference
from obi_one.scientific.unions.unions_timestamps import TimestampsReference


def _set_block_name(block: object, name: str) -> None:
    block._block_name = name


def _make_time_distribution_stimulus(
    *,
    duration: float = 25.0,
    number_of_spikes: int = 3,
    resample_each_repetition: bool = False,
) -> obi.SpikeTimeDistributionSpikeStimulus:
    stimulus = obi.SpikeTimeDistributionSpikeStimulus(
        distribution=obi.AllDistributionsReference(
            block_dict_name="distributions",
            block_name="time_dist",
        ),
        source_neuron_set=NeuronSetReference(
            block_dict_name="neuron_sets",
            block_name="test_neurons",
        ),
        timestamps=TimestampsReference(
            block_dict_name="timestamps",
            block_name="test_timestamps",
        ),
        duration=duration,
        number_of_spikes=number_of_spikes,
        resample_each_repetition=resample_each_repetition,
    )
    _set_block_name(stimulus, "test_stimulus")
    return stimulus


def _patch_distribution_ref(
    monkeypatch: pytest.MonkeyPatch,
    stimulus: obi.SpikeTimeDistributionSpikeStimulus,
    distribution: object,
) -> None:
    def _distribution_block(_ref_self: object) -> object:
        return distribution

    monkeypatch.setattr(type(stimulus.distribution), "block", property(_distribution_block))


def _patch_source_neuron_set_ref(
    monkeypatch: pytest.MonkeyPatch,
    stimulus: object,
    neuron_set: object,
) -> None:
    def _source_block(_ref_self: object) -> object:
        return neuron_set

    monkeypatch.setattr(type(stimulus.source_neuron_set), "block", property(_source_block))


def _patch_timestamps_ref(
    monkeypatch: pytest.MonkeyPatch,
    stimulus: object,
    timestamps: object,
) -> None:
    def _timestamps_block(_ref_self: object) -> object:
        return timestamps

    monkeypatch.setattr(type(stimulus.timestamps), "block", property(_timestamps_block))


def _patch_neuron_set_methods(
    monkeypatch: pytest.MonkeyPatch,
    neuron_set: object,
    *,
    neuron_ids: list[int],
    population: str = "test_pop",
) -> None:
    def _get_neuron_ids(_self: object, _circuit: object, _pop: object) -> list[int]:
        return neuron_ids

    def _get_population(_self: object, _pop: object) -> str:
        return population

    monkeypatch.setattr(type(neuron_set), "get_neuron_ids", _get_neuron_ids)
    monkeypatch.setattr(type(neuron_set), "get_population", _get_population)


def _patch_resolved_timestamps(
    monkeypatch: pytest.MonkeyPatch,
    values: list[float],
) -> None:
    mock_timestamps_block = MagicMock()
    mock_timestamps_block.enumerate_non_negative_offset_timestamps.return_value = [
        (idx, value) for idx, value in enumerate(values)
    ]
    mock_timestamps_block.timestamps.return_value = values

    def _resolve_timestamps(_ref: object, _default: object) -> object:
        return mock_timestamps_block

    monkeypatch.setattr(
        "obi_one.scientific.blocks.stimuli.stimulus.resolve_timestamps_ref_to_timestamps_block",
        _resolve_timestamps,
    )


class TestSampleSpikeTimesFromDistribution:
    def test_samples_are_sorted(self):
        dist = obi.FloatConstantDistribution(value=10.0)

        spikes = SpikeTimeDistributionSpikeStimulus._sample_spike_times_from_distribution(
            dist,
            number_of_spikes=3,
            duration=25.0,
        )

        assert spikes == [10.0, 10.0, 10.0]

    def test_samples_outside_duration_are_filtered(self):
        mock_dist = MagicMock()
        mock_dist.sample.return_value = [5.0, 30.0, 10.0, -1.0]

        spikes = SpikeTimeDistributionSpikeStimulus._sample_spike_times_from_distribution(
            mock_dist,
            number_of_spikes=4,
            duration=25.0,
        )

        assert spikes == [5.0, 10.0]

    def test_zero_number_of_spikes_returns_empty(self):
        dist = obi.FloatConstantDistribution(value=10.0)

        spikes = SpikeTimeDistributionSpikeStimulus._sample_spike_times_from_distribution(
            dist,
            number_of_spikes=0,
            duration=25.0,
        )

        assert spikes == []


class TestSpikeTimeDistributionSpikeStimulus:
    def test_generated_spike_file_has_correct_structure(self, tmp_path, monkeypatch):
        neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="test", elements=[0, 1, 2]))
        distribution = obi.FloatConstantDistribution(value=10.0)
        timestamps = obi.SingleTimestamp(start_time=0.0)
        stimulus = _make_time_distribution_stimulus(
            duration=25.0,
            number_of_spikes=2,
            resample_each_repetition=False,
        )

        _patch_distribution_ref(monkeypatch, stimulus, distribution)
        _patch_source_neuron_set_ref(monkeypatch, stimulus, neuron_set)
        _patch_timestamps_ref(monkeypatch, stimulus, timestamps)
        _patch_neuron_set_methods(monkeypatch, neuron_set, neuron_ids=[0, 1, 2])
        _patch_resolved_timestamps(monkeypatch, [5.0, 45.0])

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_directory=tmp_path,
            source_neuron_set=neuron_set,
            source_node_population="test_pop",
        )

        spike_file = tmp_path / f"{stimulus.block_name}_spikes.h5"
        assert spike_file.exists()

        with h5py.File(spike_file, "r") as f:
            assert "/spikes/test_pop/timestamps" in f
            assert "/spikes/test_pop/node_ids" in f
            assert f["/spikes/test_pop/timestamps"].attrs["units"] == "ms"
            actual = sorted(f["/spikes/test_pop/timestamps"][:].tolist())

        expected = sorted([15.0, 15.0, 55.0, 55.0] * 3)
        assert actual == expected

    def test_resample_each_repetition_false_reuses_relative_pattern(
        self,
        tmp_path,
        monkeypatch,
    ):
        neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="test", elements=[0, 1, 2]))
        distribution = obi.FloatUniformDistribution(low=0.0, high=25.0, random_seed=42)
        timestamps = obi.SingleTimestamp(start_time=0.0)
        stimulus = _make_time_distribution_stimulus(
            duration=25.0,
            number_of_spikes=5,
            resample_each_repetition=False,
        )

        _patch_distribution_ref(monkeypatch, stimulus, distribution)
        _patch_source_neuron_set_ref(monkeypatch, stimulus, neuron_set)
        _patch_timestamps_ref(monkeypatch, stimulus, timestamps)
        _patch_neuron_set_methods(monkeypatch, neuron_set, neuron_ids=[0, 1, 2])
        _patch_resolved_timestamps(monkeypatch, [0.0, 50.0])

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_directory=tmp_path,
            source_neuron_set=neuron_set,
            source_node_population="test_pop",
        )

        spike_file = tmp_path / f"{stimulus.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            timestamps_out = sorted(f["/spikes/test_pop/timestamps"][:].tolist())

        first_rep = [t for t in timestamps_out if t < 25.0]
        second_rep = [t - 50.0 for t in timestamps_out if 50.0 <= t < 75.0]
        np.testing.assert_allclose(first_rep, second_rep)

    def test_resample_each_repetition_true_regenerates_pattern(
        self,
        tmp_path,
        monkeypatch,
    ):
        neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="test", elements=[0, 1, 2]))
        distribution = obi.FloatUniformDistribution(low=0.0, high=25.0, random_seed=42)
        timestamps = obi.SingleTimestamp(start_time=0.0)
        stimulus = _make_time_distribution_stimulus(
            duration=25.0,
            number_of_spikes=5,
            resample_each_repetition=True,
        )

        _patch_distribution_ref(monkeypatch, stimulus, distribution)
        _patch_source_neuron_set_ref(monkeypatch, stimulus, neuron_set)
        _patch_timestamps_ref(monkeypatch, stimulus, timestamps)
        _patch_neuron_set_methods(monkeypatch, neuron_set, neuron_ids=[0, 1, 2])
        _patch_resolved_timestamps(monkeypatch, [0.0, 50.0])

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_directory=tmp_path,
            source_neuron_set=neuron_set,
            source_node_population="test_pop",
        )

        spike_file = tmp_path / f"{stimulus.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            timestamps_out = f["/spikes/test_pop/timestamps"][:].tolist()

        first_rep = sorted(t for t in timestamps_out if t < 25.0)
        second_rep = sorted(t - 50.0 for t in timestamps_out if 50.0 <= t < 75.0)
        assert not np.allclose(first_rep, second_rep)

    def test_default_distribution_is_uniform_over_duration(self, monkeypatch):
        stimulus = _make_time_distribution_stimulus(duration=25.0, number_of_spikes=3)
        stimulus.distribution = None

        mock_sample = MagicMock(return_value=[1.0, 2.0, 3.0])
        monkeypatch.setattr(
            SpikeTimeDistributionSpikeStimulus,
            "_sample_spike_times_from_distribution",
            mock_sample,
        )

        _patch_resolved_timestamps(monkeypatch, [0.0])

        stimulus.generate_spikes_by_gid([0])

        distribution = mock_sample.call_args.args[0]
        assert isinstance(distribution, obi.FloatUniformDistribution)
        assert distribution.low == 0.0  # noqa: RUF069
        assert distribution.high == 25.0  # noqa: RUF069


class TestSpikeTimeStimulusIndexingConvention:
    def test_node_ids_follow_current_indexing_convention(self, tmp_path, monkeypatch):
        neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="test", elements=[5, 10, 15]))
        distribution = obi.FloatConstantDistribution(value=10.0)
        timestamps = obi.SingleTimestamp(start_time=0.0)
        stimulus = _make_time_distribution_stimulus(duration=25.0, number_of_spikes=2)

        _patch_distribution_ref(monkeypatch, stimulus, distribution)
        _patch_source_neuron_set_ref(monkeypatch, stimulus, neuron_set)
        _patch_timestamps_ref(monkeypatch, stimulus, timestamps)
        _patch_neuron_set_methods(monkeypatch, neuron_set, neuron_ids=[5, 10, 15])
        _patch_resolved_timestamps(monkeypatch, [0.0])

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_directory=tmp_path,
            source_neuron_set=neuron_set,
            source_node_population="test_pop",
        )

        spike_file = tmp_path / f"{stimulus.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            node_ids = sorted(set(f["/spikes/test_pop/node_ids"][:].tolist()))

        assert node_ids == [5, 10, 15]

import h5py
import pytest
from unittest.mock import MagicMock

import obi_one as obi
from obi_one.scientific.blocks.stimuli.stimulus import SpikeStimulus
from obi_one.scientific.unions.unions_neuron_sets import NeuronSetReference
from obi_one.scientific.unions.unions_timestamps import TimestampsReference


class TestSpikeStimulusGenerateSpikeTrainFromDistribution:
    def test_constant_distribution_basic_case(self):
        dist = obi.FloatConstantDistribution(value=10.0)
        spikes = SpikeStimulus._generate_spike_train_from_distribution(dist, duration=35.0)
        assert spikes == [10.0, 20.0, 30.0]

    def test_returned_spike_times_strictly_increasing(self):
        dist = obi.ExponentialDistribution(scale=5.0, random_seed=42)
        spikes = SpikeStimulus._generate_spike_train_from_distribution(dist, duration=50.0)
        assert all(spikes[i] < spikes[i + 1] for i in range(len(spikes) - 1))

    def test_returned_spike_times_all_less_than_duration(self):
        dist = obi.GammaDistribution(shape=2.0, scale=3.0, random_seed=42)
        spikes = SpikeStimulus._generate_spike_train_from_distribution(dist, duration=25.0)
        assert all(s < 25.0 for s in spikes)

    def test_non_positive_intervals_raise_value_error(self):
        mock_dist = MagicMock()
        mock_dist.sample.return_value = [-1.0]

        with pytest.raises(ValueError, match="Inter-spike intervals must be positive"):
            SpikeStimulus._generate_spike_train_from_distribution(mock_dist, duration=10.0)


class TestDistributionSpikeStimulus:
    def test_generated_spike_file_has_correct_structure(self, tmp_path, monkeypatch):
        neuron_set = obi.IDNeuronSet(
            neuron_ids=obi.NamedTuple(name="test", elements=[0, 1, 2])
        )
        distribution = obi.FloatConstantDistribution(value=10.0)
        timestamps = obi.SingleTimestamp(start_time=0.0)

        stimulus = obi.DistributionSpikeStimulus(
            distribution=obi.AllDistributionsReference(
                block_dict_name="distributions",
                block_name="constant_dist",
            ),
            source_neuron_set=NeuronSetReference(
                block_dict_name="neuron_sets",
                block_name="test_neurons",
            ),
            timestamps=TimestampsReference(
                block_dict_name="timestamps",
                block_name="test_timestamps",
            ),
            duration=25.0,
            resample_each_repetition=False,
        )
        stimulus._block_name = "test_stimulus"

        monkeypatch.setattr(type(stimulus.distribution), "block", property(lambda self: distribution))
        monkeypatch.setattr(type(stimulus.source_neuron_set), "block", property(lambda self: neuron_set))
        monkeypatch.setattr(type(stimulus.timestamps), "block", property(lambda self: timestamps))

        monkeypatch.setattr(
            type(neuron_set),
            "get_neuron_ids",
            lambda self, circuit, pop: [0, 1, 2],
        )
        monkeypatch.setattr(
            type(neuron_set),
            "get_population",
            lambda self, pop: "test_pop",
        )

        mock_timestamps_block = MagicMock()
        mock_timestamps_block.timestamps.return_value = [5.0, 45.0]
        monkeypatch.setattr(
            "obi_one.scientific.blocks.stimuli.stimulus.resolve_timestamps_ref_to_timestamps_block",
            lambda ref, default: mock_timestamps_block,
        )

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_path=tmp_path,
            simulation_length=100.0,
        )

        spike_file = tmp_path / f"{stimulus.block_name}_spikes.h5"
        assert spike_file.exists()

        with h5py.File(spike_file, "r") as f:
            assert "/spikes/test_pop/timestamps" in f
            assert "/spikes/test_pop/node_ids" in f
            assert f["/spikes/test_pop/timestamps"].attrs["units"] == "ms"
            actual = sorted(f["/spikes/test_pop/timestamps"][:].tolist())

        expected = sorted([15.0, 25.0, 55.0, 65.0] * 3)
        assert actual == expected


class TestSpikeStimulusIndexingConvention:
    def test_node_ids_follow_current_indexing_convention(self, tmp_path, monkeypatch):
        neuron_set = obi.IDNeuronSet(
            neuron_ids=obi.NamedTuple(name="test", elements=[5, 10, 15])
        )
        distribution = obi.FloatConstantDistribution(value=10.0)
        timestamps = obi.SingleTimestamp(start_time=0.0)

        stimulus = obi.DistributionSpikeStimulus(
            distribution=obi.AllDistributionsReference(
                block_dict_name="distributions",
                block_name="constant_dist",
            ),
            source_neuron_set=NeuronSetReference(
                block_dict_name="neuron_sets",
                block_name="test_neurons",
            ),
            timestamps=TimestampsReference(
                block_dict_name="timestamps",
                block_name="test_timestamps",
            ),
            duration=25.0,
        )
        stimulus._block_name = "test_stimulus"

        monkeypatch.setattr(type(stimulus.distribution), "block", property(lambda self: distribution))
        monkeypatch.setattr(type(stimulus.source_neuron_set), "block", property(lambda self: neuron_set))
        monkeypatch.setattr(type(stimulus.timestamps), "block", property(lambda self: timestamps))

        monkeypatch.setattr(
            type(neuron_set),
            "get_neuron_ids",
            lambda self, circuit, pop: [5, 10, 15],
        )
        monkeypatch.setattr(
            type(neuron_set),
            "get_population",
            lambda self, pop: "test_pop",
        )

        mock_timestamps_block = MagicMock()
        mock_timestamps_block.timestamps.return_value = [0.0]
        monkeypatch.setattr(
            "obi_one.scientific.blocks.stimuli.stimulus.resolve_timestamps_ref_to_timestamps_block",
            lambda ref, default: mock_timestamps_block,
        )

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_path=tmp_path,
            simulation_length=100.0,
        )

        spike_file = tmp_path / f"{stimulus.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            node_ids = sorted(set(f["/spikes/test_pop/node_ids"][:].tolist()))

        assert node_ids == [5, 10, 15]


class TestPoissonSpikeStimulus:
    def test_uses_shared_distribution_path(self, monkeypatch):
        neuron_set = obi.IDNeuronSet(
            neuron_ids=obi.NamedTuple(name="test", elements=[0])
        )
        timestamps = obi.SingleTimestamp(start_time=0.0)

        stimulus = obi.PoissonSpikeStimulus(
            frequency=20.0,
            random_seed=42,
            source_neuron_set=NeuronSetReference(
                block_dict_name="neuron_sets",
                block_name="test_neurons",
            ),
            timestamps=TimestampsReference(
                block_dict_name="timestamps",
                block_name="test_timestamps",
            ),
            duration=50.0,
        )
        stimulus._block_name = "poisson_stimulus"

        monkeypatch.setattr(type(stimulus.source_neuron_set), "block", property(lambda self: neuron_set))
        monkeypatch.setattr(type(stimulus.timestamps), "block", property(lambda self: timestamps))

        mock_generate = MagicMock()
        monkeypatch.setattr(stimulus, "_generate_spikes_from_distribution", mock_generate)

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_path=MagicMock(),
            simulation_length=100.0,
        )

        mock_generate.assert_called_once()
        dist = mock_generate.call_args.kwargs["distribution"]
        assert isinstance(dist, obi.ExponentialDistribution)

    def test_distribution_scale_matches_frequency(self, monkeypatch):
        neuron_set = obi.IDNeuronSet(
            neuron_ids=obi.NamedTuple(name="test", elements=[0])
        )
        timestamps = obi.SingleTimestamp(start_time=0.0)

        stimulus = obi.PoissonSpikeStimulus(
            frequency=20.0,
            random_seed=42,
            source_neuron_set=NeuronSetReference(
                block_dict_name="neuron_sets",
                block_name="test_neurons",
            ),
            timestamps=TimestampsReference(
                block_dict_name="timestamps",
                block_name="test_timestamps",
            ),
            duration=50.0,
        )
        stimulus._block_name = "poisson_stimulus"

        monkeypatch.setattr(type(stimulus.source_neuron_set), "block", property(lambda self: neuron_set))
        monkeypatch.setattr(type(stimulus.timestamps), "block", property(lambda self: timestamps))

        mock_generate = MagicMock()
        monkeypatch.setattr(stimulus, "_generate_spikes_from_distribution", mock_generate)

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_path=MagicMock(),
            simulation_length=100.0,
        )

        dist = mock_generate.call_args.kwargs["distribution"]
        assert dist.scale == 50.0

    def test_random_seed_forwarded_to_distribution(self, monkeypatch):
        neuron_set = obi.IDNeuronSet(
            neuron_ids=obi.NamedTuple(name="test", elements=[0])
        )
        timestamps = obi.SingleTimestamp(start_time=0.0)

        stimulus = obi.PoissonSpikeStimulus(
            frequency=10.0,
            random_seed=123,
            source_neuron_set=NeuronSetReference(
                block_dict_name="neuron_sets",
                block_name="test_neurons",
            ),
            timestamps=TimestampsReference(
                block_dict_name="timestamps",
                block_name="test_timestamps",
            ),
            duration=50.0,
        )
        stimulus._block_name = "poisson_stimulus"

        monkeypatch.setattr(type(stimulus.source_neuron_set), "block", property(lambda self: neuron_set))
        monkeypatch.setattr(type(stimulus.timestamps), "block", property(lambda self: timestamps))

        mock_generate = MagicMock()
        monkeypatch.setattr(stimulus, "_generate_spikes_from_distribution", mock_generate)

        stimulus.generate_spikes(
            circuit=MagicMock(),
            spike_file_path=MagicMock(),
            simulation_length=100.0,
        )

        dist = mock_generate.call_args.kwargs["distribution"]
        assert dist.random_seed == 123

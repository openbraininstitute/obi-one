import h5py
import numpy as np

import obi_one as obi
from obi_one.scientific.blocks.stimuli.spike.fully_synchronous import (
    FullySynchronousSpikeStimulus,
)

from .conftest import generate_spikes_for_stim, make_validated_stimulus


class TestFullySynchronousSpikeStimulus:
    def test_all_gids_spike_at_each_timestamp(self, tmp_path):
        source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
        target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))
        timestamps = obi.RegularTimestamps(start_time=100.0, number_of_repetitions=3, interval=200.0)

        vc = make_validated_stimulus(source, target, FullySynchronousSpikeStimulus, timestamps)
        stim, circuit, pop = generate_spikes_for_stim(vc, tmp_path)

        spike_file = tmp_path / f"{stim.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            ts = np.array(f[f"spikes/{pop}/timestamps"])
            nids = np.array(f[f"spikes/{pop}/node_ids"])

        source_gids = source.get_neuron_ids(circuit, circuit.default_population_name)
        expected_times = timestamps.timestamps()

        # Each source gid should have exactly one spike per timestamp
        assert len(ts) == len(source_gids) * len(expected_times)

        for gid in source_gids:
            gid_times = sorted(ts[nids == gid])
            np.testing.assert_array_almost_equal(gid_times, expected_times)

    def test_with_timestamp_offset(self, tmp_path):
        source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
        target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))
        timestamps = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=2, interval=500.0)

        vc = make_validated_stimulus(
            source, target, FullySynchronousSpikeStimulus, timestamps, timestamp_offset=50.0,
        )
        stim, circuit, pop = generate_spikes_for_stim(vc, tmp_path)

        spike_file = tmp_path / f"{stim.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            ts = np.array(f[f"spikes/{pop}/timestamps"])

        expected_times = [t + 50.0 for t in timestamps.timestamps()]
        unique_times = sorted(set(ts))
        np.testing.assert_array_almost_equal(unique_times, expected_times)

    def test_default_single_timestamp_when_none(self, tmp_path):
        """When timestamps=None, should use the default SingleTimestamp(start_time=0.0)."""
        source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
        target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))

        vc = make_validated_stimulus(source, target, FullySynchronousSpikeStimulus, timestamps=None)
        stim, circuit, pop = generate_spikes_for_stim(vc, tmp_path)

        spike_file = tmp_path / f"{stim.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            ts = np.array(f[f"spikes/{pop}/timestamps"])

        # Default SingleTimestamp(start_time=0.0) → all spikes at t=0.0
        np.testing.assert_array_equal(ts, np.zeros(len(ts)))
        assert len(ts) == 3  # one spike per source gid

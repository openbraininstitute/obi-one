import h5py
import numpy as np
import pytest

from obi_one.scientific.blocks.stimuli.spike.base import SpikeStimulus


class TestWriteSpikeFile:
    def test_writes_sorted_spike_file(self, tmp_path):
        spike_file = tmp_path / "spikes.h5"
        spikes_by_gid = {
            0: [10.0, 5.0, 20.0],
            1: [3.0, 15.0],
        }
        SpikeStimulus.write_spike_file(spikes_by_gid, spike_file, "NodeA")

        with h5py.File(spike_file, "r") as f:
            ts = np.array(f["spikes/NodeA/timestamps"])
            nids = np.array(f["spikes/NodeA/node_ids"])
            assert f["spikes/NodeA/timestamps"].attrs["units"] == "ms"

        # Timestamps should be sorted
        np.testing.assert_array_equal(ts, np.sort(ts))
        assert len(ts) == 5
        assert len(nids) == 5

    def test_empty_spikes(self, tmp_path):
        spike_file = tmp_path / "empty.h5"
        SpikeStimulus.write_spike_file({}, spike_file, "NodeA")

        with h5py.File(spike_file, "r") as f:
            ts = np.array(f["spikes/NodeA/timestamps"])
            nids = np.array(f["spikes/NodeA/node_ids"])

        assert len(ts) == 0
        assert len(nids) == 0

    def test_creates_parent_directories(self, tmp_path):
        spike_file = tmp_path / "nested" / "dir" / "spikes.h5"
        SpikeStimulus.write_spike_file({0: [1.0]}, spike_file, "pop")
        assert spike_file.exists()


class TestResolvedTimestampsProperty:
    def test_raises_before_generate_spikes(self):
        from obi_one.scientific.blocks.stimuli.spike.fully_synchronous import (
            FullySynchronousSpikeStimulus,
        )

        stim = FullySynchronousSpikeStimulus()
        with pytest.raises(ValueError, match="Timestamps must be resolved"):
            _ = stim.resolved_timestamps

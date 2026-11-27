import h5py
import numpy as np
import pytest

from obi_one.scientific.library import replay_inputs as module
from obi_one.scientific.library.replay_inputs import ReplayCounts, count_replay, replayed_synapses

SIZES = {"VPM": 10, "POm": 4, "cells": 5}


def write_spikes(path, spikes_by_population):
    with h5py.File(path, "w") as f:
        for population, node_ids in spikes_by_population.items():
            group = f.create_group(f"spikes/{population}")
            group.create_dataset("node_ids", data=np.array(node_ids, dtype=np.uint64))
            group.create_dataset("timestamps", data=np.arange(len(node_ids), dtype=np.float64))
    return path


class TestCountReplay:
    def test_the_spikes_and_the_nodes_that_spike(self, tmp_path):
        spikes = write_spikes(tmp_path / "a.h5", {"VPM": [1, 1, 2, 7], "POm": [0]})

        counts = count_replay([spikes], SIZES)

        assert counts == ReplayCounts(sources={"VPM": 3, "POm": 1}, spikes=5)

    def test_a_node_spiking_in_several_files_counts_once(self, tmp_path):
        a = write_spikes(tmp_path / "a.h5", {"VPM": [1, 2]})
        b = write_spikes(tmp_path / "b.h5", {"VPM": [2, 3]})

        counts = count_replay([a, b], SIZES)

        assert counts == ReplayCounts(sources={"VPM": 3}, spikes=4)

    def test_node_ids_are_read_in_chunks(self, tmp_path, monkeypatch):
        monkeypatch.setattr(module, "CHUNK", 2)
        spikes = write_spikes(tmp_path / "a.h5", {"VPM": [0, 1, 2, 3, 4, 4, 9]})

        assert count_replay([spikes], SIZES) == ReplayCounts(sources={"VPM": 6}, spikes=7)

    def test_a_population_not_in_the_circuit_counts_its_spikes_only(self, tmp_path):
        """Every rank still reads these spikes, but no synapse replays them."""
        spikes = write_spikes(tmp_path / "a.h5", {"elsewhere": [0, 1]})

        assert count_replay([spikes], SIZES) == ReplayCounts(sources={}, spikes=2)

    def test_node_ids_beyond_the_population_are_ignored(self, tmp_path):
        spikes = write_spikes(tmp_path / "a.h5", {"POm": [0, 4, 100]})

        assert count_replay([spikes], SIZES) == ReplayCounts(sources={"POm": 1}, spikes=3)

    def test_no_spike_file_replays_nothing(self):
        assert count_replay([], SIZES) == ReplayCounts()


class TestReplayedSynapses:
    def test_a_population_replays_its_share_of_synapses_times_the_margin(self):
        replayed = replayed_synapses({"VPM": 1000.0, "cells": 500.0}, {"VPM": 1}, SIZES)

        assert replayed == round(1000 * module.WORST_CASE_SUBSET_DENSITY_VS_AVERAGE / 10)

    def test_the_share_is_capped_at_all_the_synapses_of_the_population(self):
        sources = {"VPM": 5, "POm": 4}

        assert replayed_synapses({"VPM": 1000.0, "POm": 300.0}, sources, SIZES) == 1300

    @pytest.mark.parametrize("sources", [{}, {"VPM": 0}])
    def test_no_spiking_source_replays_nothing(self, sources):
        assert replayed_synapses({"VPM": 1000.0}, sources, SIZES) == 0

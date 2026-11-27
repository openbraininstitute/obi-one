from pathlib import Path

from obi_one.scientific.library.simulation_synapses import replay_spike_files


def test_the_spike_files_of_the_replay_inputs_only(tmp_path):
    config = {
        "inputs": {
            "volley": {"module": "synapse_replay", "spike_file": "volley_spikes.h5"},
            "clamp": {"module": "linear", "amp_start": 0.1},
            "empty": {"module": "synapse_replay", "spike_file": None},
        }
    }

    assert replay_spike_files(config, tmp_path) == [Path(tmp_path, "volley_spikes.h5")]


def test_a_config_without_inputs_has_no_spike_files(tmp_path):
    assert replay_spike_files({}, tmp_path) == []

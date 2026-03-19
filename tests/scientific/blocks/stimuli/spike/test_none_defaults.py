"""Tests for spike stimuli when neuron sets and timestamps are None.

These should resolve to defaults (default_node_set, default_timestamps).
"""

import h5py
import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.stimuli.spike.fully_synchronous import (
    FullySynchronousSpikeStimulus,
)
from obi_one.scientific.blocks.stimuli.spike.poisson import PoissonSpikeStimulus
from obi_one.scientific.unions.unions_neuron_sets import resolve_neuron_set_ref_to_node_set

from .conftest import generate_spikes_for_stim, make_validated_stimulus


class TestNoneTargetedNeuronSet:
    """When targeted_neuron_set=None, the node_set should resolve to default."""

    def test_resolve_neuron_set_ref_returns_default_when_none(self):
        result = resolve_neuron_set_ref_to_node_set(None, "MyDefault")
        assert result == "MyDefault"

    def test_generate_config_uses_default_node_set_when_target_is_none(self):
        """_generate_config should use default_node_set when targeted_neuron_set is None."""
        sc = obi.CircuitSimulationScanConfig.empty_config()
        stim = FullySynchronousSpikeStimulus()
        sc.add(stim, name="stim")

        # Set internals that would be set by config() + generate_spikes()
        stim._default_node_set = "MyDefaultNodeSet"
        stim._spike_file = "test_spikes.h5"
        stim._simulation_length = 1000.0

        config = stim._generate_config()
        assert config["stim"]["node_set"] == "MyDefaultNodeSet"


class TestNoneSourceNeuronSet:
    """When source_neuron_set=None, generate_spikes should fail.

    generate_spikes calls self.source_neuron_set.block.get_neuron_ids(...)
    which will raise AttributeError since None has no .block attribute.
    """

    def test_generate_spikes_with_none_source_raises(self, tmp_path):
        sc = obi.CircuitSimulationScanConfig.empty_config()
        stim = FullySynchronousSpikeStimulus()
        sc.add(stim, name="stim")

        stim._default_node_set = "All"
        stim._default_timestamps = obi.SingleTimestamp(start_time=0.0)

        from .conftest import STIM_CIRCUIT

        with pytest.raises(AttributeError):
            stim.generate_spikes(
                STIM_CIRCUIT, tmp_path, simulation_length=1000.0,
                source_node_population=STIM_CIRCUIT.default_population_name,
            )


class TestNoneTimestamps:
    """When timestamps=None, should fall back to default SingleTimestamp(start_time=0.0)."""

    def test_synchronous_generates_spikes_at_time_zero(self, tmp_path):
        source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
        target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))

        vc = make_validated_stimulus(
            source, target, FullySynchronousSpikeStimulus, timestamps=None,
        )
        stim, circuit, pop = generate_spikes_for_stim(vc, tmp_path)

        spike_file = tmp_path / f"{stim.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            ts = np.array(f[f"spikes/{pop}/timestamps"])

        # Default SingleTimestamp(start_time=0.0) → all spikes at t=0.0
        np.testing.assert_array_equal(ts, np.zeros(len(ts)))
        assert len(ts) == 3  # one spike per source gid

    def test_poisson_with_none_timestamps_uses_default(self, tmp_path):
        source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
        target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))

        vc = make_validated_stimulus(
            source, target, PoissonSpikeStimulus, timestamps=None,
            duration=100.0, frequency=50.0, random_seed=42,
        )
        stim, circuit, pop = generate_spikes_for_stim(vc, tmp_path)

        spike_file = tmp_path / f"{stim.block_name}_spikes.h5"
        with h5py.File(spike_file, "r") as f:
            ts = np.array(f[f"spikes/{pop}/timestamps"])

        assert len(ts) > 0
        # Spikes should be within [0, 100) since default timestamp is 0.0 and duration=100
        assert np.all(ts >= 0.0)
        assert np.all(ts < 100.0)

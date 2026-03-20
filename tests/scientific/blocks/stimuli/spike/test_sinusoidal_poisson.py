import h5py
import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.stimuli.spike.sinusoidal_poisson import (
    SinusoidalPoissonSpikeStimulus,
)

from .conftest import generate_spikes_for_stim, make_validated_stimulus


def test_spikes_within_time_window(tmp_path):
    source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
    target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))
    timestamps = obi.RegularTimestamps(start_time=100.0, number_of_repetitions=1, interval=1000.0)
    duration = 500.0

    vc = make_validated_stimulus(
        source,
        target,
        SinusoidalPoissonSpikeStimulus,
        timestamps,
        duration=duration,
        minimum_rate=1.0,
        maximum_rate=20.0,
        modulation_frequency_hz=5.0,
        random_seed=42,
    )
    stim, _circuit, pop = generate_spikes_for_stim(vc, tmp_path)

    spike_file = tmp_path / f"{stim.block_name}_spikes.h5"
    with h5py.File(spike_file, "r") as f:
        ts = np.array(f[f"spikes/{pop}/timestamps"])

    assert len(ts) > 0
    assert np.all(ts >= 100.0)
    assert np.all(ts < 100.0 + duration)


def test_reproducible_with_same_seed(tmp_path):
    kwargs = {
        "duration": 300.0,
        "minimum_rate": 1.0,
        "maximum_rate": 10.0,
        "modulation_frequency_hz": 5.0,
        "random_seed": 7,
    }

    source1 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="s1", elements=range(3)))
    target1 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="t1", elements=range(10)))
    stim1, _, pop1 = generate_spikes_for_stim(
        make_validated_stimulus(
            source1,
            target1,
            SinusoidalPoissonSpikeStimulus,
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=1000.0),
            **kwargs,
        ),
        tmp_path / "r1",
    )

    source2 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="s2", elements=range(3)))
    target2 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="t2", elements=range(10)))
    stim2, _, pop2 = generate_spikes_for_stim(
        make_validated_stimulus(
            source2,
            target2,
            SinusoidalPoissonSpikeStimulus,
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=1000.0),
            **kwargs,
        ),
        tmp_path / "r2",
    )

    with h5py.File(tmp_path / "r1" / f"{stim1.block_name}_spikes.h5", "r") as f:
        ts1_data = np.array(f[f"spikes/{pop1}/timestamps"])
    with h5py.File(tmp_path / "r2" / f"{stim2.block_name}_spikes.h5", "r") as f:
        ts2_data = np.array(f[f"spikes/{pop2}/timestamps"])

    np.testing.assert_array_equal(ts1_data, ts2_data)


def test_max_rate_less_than_min_rate_raises():
    with pytest.raises(ValueError, match="Maximum rate must be greater"):
        SinusoidalPoissonSpikeStimulus(
            minimum_rate=10.0,
            maximum_rate=1.0,
        )


def test_overlapping_timestamps_raises(tmp_path):
    source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
    target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))
    timestamps = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=3, interval=50.0)

    vc = make_validated_stimulus(
        source,
        target,
        SinusoidalPoissonSpikeStimulus,
        timestamps,
        duration=200.0,
        minimum_rate=1.0,
        maximum_rate=10.0,
        modulation_frequency_hz=5.0,
    )
    with pytest.raises(ValueError, match="Stimulus time intervals overlap"):
        generate_spikes_for_stim(vc, tmp_path)

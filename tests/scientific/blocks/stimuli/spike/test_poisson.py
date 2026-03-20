import h5py
import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.stimuli.spike.poisson import PoissonSpikeStimulus

from .conftest import generate_spikes_for_stim, make_validated_stimulus


def test_spikes_within_time_window(tmp_path):
    source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
    target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))
    timestamps = obi.RegularTimestamps(start_time=100.0, number_of_repetitions=2, interval=500.0)
    duration = 200.0
    offset = 10.0

    vc = make_validated_stimulus(
        source,
        target,
        PoissonSpikeStimulus,
        timestamps,
        duration=duration,
        frequency=50.0,
        random_seed=42,
        timestamp_offset=offset,
    )
    stim, _circuit, pop = generate_spikes_for_stim(vc, tmp_path)

    spike_file = tmp_path / f"{stim.block_name}_spikes.h5"
    with h5py.File(spike_file, "r") as f:
        ts = np.array(f[f"spikes/{pop}/timestamps"])

    assert len(ts) > 0

    # No spikes outside any window
    for t in ts:
        in_some_window = any(
            t_start + offset <= t < t_start + offset + duration
            for t_start in timestamps.timestamps()
        )
        assert in_some_window, f"Spike at t={t} is outside all stimulus windows"


def test_reproducible_with_same_seed(tmp_path):
    kwargs = {"duration": 500.0, "frequency": 10.0, "random_seed": 123}

    source1 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="s1", elements=range(3)))
    target1 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="t1", elements=range(10)))
    stim1, _, pop1 = generate_spikes_for_stim(
        make_validated_stimulus(
            source1,
            target1,
            PoissonSpikeStimulus,
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=1000.0),
            **kwargs,
        ),
        tmp_path / "run1",
    )

    source2 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="s2", elements=range(3)))
    target2 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="t2", elements=range(10)))
    stim2, _, pop2 = generate_spikes_for_stim(
        make_validated_stimulus(
            source2,
            target2,
            PoissonSpikeStimulus,
            obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=1000.0),
            **kwargs,
        ),
        tmp_path / "run2",
    )

    with h5py.File(tmp_path / "run1" / f"{stim1.block_name}_spikes.h5", "r") as f:
        ts1_data = np.array(f[f"spikes/{pop1}/timestamps"])
    with h5py.File(tmp_path / "run2" / f"{stim2.block_name}_spikes.h5", "r") as f:
        ts2_data = np.array(f[f"spikes/{pop2}/timestamps"])

    np.testing.assert_array_equal(ts1_data, ts2_data)


def test_different_seed_produces_different_spikes(tmp_path):
    source1 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="s1", elements=range(3)))
    target1 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="t1", elements=range(10)))
    ts1 = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=1000.0)
    vc1 = make_validated_stimulus(
        source1,
        target1,
        PoissonSpikeStimulus,
        ts1,
        duration=500.0,
        frequency=10.0,
        random_seed=1,
    )
    stim1, _, pop1 = generate_spikes_for_stim(vc1, tmp_path / "seed1")

    source2 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="s2", elements=range(3)))
    target2 = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="t2", elements=range(10)))
    ts2 = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=1, interval=1000.0)
    vc2 = make_validated_stimulus(
        source2,
        target2,
        PoissonSpikeStimulus,
        ts2,
        duration=500.0,
        frequency=10.0,
        random_seed=999,
    )
    stim2, _, pop2 = generate_spikes_for_stim(vc2, tmp_path / "seed2")

    with h5py.File(tmp_path / "seed1" / f"{stim1.block_name}_spikes.h5", "r") as f:
        ts1_data = np.array(f[f"spikes/{pop1}/timestamps"])
    with h5py.File(tmp_path / "seed2" / f"{stim2.block_name}_spikes.h5", "r") as f:
        ts2_data = np.array(f[f"spikes/{pop2}/timestamps"])

    assert not np.array_equal(ts1_data, ts2_data)


def test_overlapping_timestamps_raises(tmp_path):
    # Interval=100 but duration=200 → overlap
    source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
    target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))
    timestamps = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=3, interval=100.0)

    vc = make_validated_stimulus(
        source,
        target,
        PoissonSpikeStimulus,
        timestamps,
        duration=200.0,
        frequency=10.0,
    )
    with pytest.raises(ValueError, match="Stimulus time intervals overlap"):
        generate_spikes_for_stim(vc, tmp_path)


def test_non_overlapping_timestamps_succeeds(tmp_path):
    # Interval=500 and duration=200 → no overlap
    source = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="src", elements=range(3)))
    target = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="tgt", elements=range(10)))
    timestamps = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=3, interval=500.0)

    vc = make_validated_stimulus(
        source,
        target,
        PoissonSpikeStimulus,
        timestamps,
        duration=200.0,
        frequency=10.0,
    )
    # Should not raise
    generate_spikes_for_stim(vc, tmp_path)

"""Timestamps and distribution blocks, exercised through the stimuli that consume them.

Neither block type emits SONATA of its own: timestamps expand a stimulus into repeated inputs,
and distributions shape the spike trains a distribution-driven stimulus writes. Both are covered
here by generating a simulation and inspecting what came out.
"""

import inspect
import typing

import h5py
import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.id import VirtualPopulationIDNeuronSet
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.distributions import AllDistributionsUnion
from obi_one.scientific.unions_and_references.timestamps import TimestampsUnion

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    VIRTUAL_POPULATION,
    build_config,
    generate,
)

TIMESTAMPS = {
    "SingleTimestamp": obi.SingleTimestamp(start_time=0.0),
    "RegularTimestamps": obi.RegularTimestamps(
        start_time=0.0, number_of_repetitions=2, interval=25.0
    ),
}

# Distributions that produce non-negative samples, so they can stand in for an inter-spike
# interval. The integer-valued ones are included because the union accepts them.
DISTRIBUTIONS = {
    "FloatConstantDistribution": obi.FloatConstantDistribution(value=10.0),
    "FloatUniformDistribution": obi.FloatUniformDistribution(low=5.0, high=15.0),
    "ExponentialDistribution": obi.ExponentialDistribution(scale=10.0),
    "GammaDistribution": obi.GammaDistribution(shape=2.0, scale=5.0),
    "NormalDistribution": obi.NormalDistribution(mean=10.0, standard_deviation=1.0, min=0.1),
    "LogNormalDistribution": obi.LogNormalDistribution(mean=2.0, sigma=0.5),
    "PoissonDistribution": obi.PoissonDistribution(rate=10.0, min=1.0),
    "IntConstantDistribution": obi.IntConstantDistribution(value=10),
    "IntUniformDistribution": obi.IntUniformDistribution(low=5, high=15),
    "IntDiscreteDistribution": obi.IntDiscreteDistribution(
        values=[5, 10, 20], probabilities=[0.3, 0.4, 0.3]
    ),
}


def _union_member_names(union) -> set[str]:
    inner = typing.get_args(union)[0]
    if inspect.isclass(inner):
        return {inner.__name__}
    return {cls.__name__ for cls in typing.get_args(inner) if inspect.isclass(cls)}


def _distribution_driven_config(circuit, distribution):
    source = VirtualPopulationIDNeuronSet(
        population=VIRTUAL_POPULATION,
        neuron_ids=obi.NamedTuple(name="source", elements=[0, 1, 2]),
    )
    return build_config(
        CircuitSimulationSingleConfig,
        circuit=circuit,
        blocks={
            "Source": source,
            "Distribution": distribution,
            "Spikes": lambda: obi.InterSpikeIntervalDistributionSpikeStimulus(
                source_neuron_set=source.ref,
                distribution=obi.AllDistributionsReference(
                    block_dict_name="distributions", block_name="Distribution"
                ),
                duration=100.0,
            ),
        },
    )


class TestUnionCoverage:
    def test_every_timestamps_block_is_exercised(self):
        assert _union_member_names(TimestampsUnion) == set(TIMESTAMPS)

    def test_every_distribution_is_exercised(self):
        assert _union_member_names(AllDistributionsUnion) == set(DISTRIBUTIONS)


class TestTimestamps:
    @pytest.mark.parametrize("name", sorted(TIMESTAMPS))
    def test_a_stimulus_can_be_driven_by_each_timestamps_block(self, name, circuit, tmp_path):
        timestamps = TIMESTAMPS[name].model_copy(deep=True)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "When": timestamps,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    timestamps=timestamps.ref, duration=5.0
                ),
            },
        )

        result = generate(config, tmp_path)

        assert len(result.inputs) == len(timestamps.timestamps())

    def test_regular_timestamps_are_evenly_spaced(self, circuit, tmp_path):
        timestamps = obi.RegularTimestamps(start_time=10.0, number_of_repetitions=4, interval=15.0)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "When": timestamps,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    timestamps=timestamps.ref, duration=5.0
                ),
            },
        )

        result = generate(config, tmp_path)

        delays = [result.inputs[f"Clamp_{i}"]["delay"] for i in range(4)]
        assert delays == [10.0, 25.0, 40.0, 55.0]

    def test_an_unused_timestamps_block_changes_nothing(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Unused": obi.RegularTimestamps(
                    start_time=0.0, number_of_repetitions=5, interval=10.0
                ),
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.inputs) == {"Clamp_0"}


class TestDistributions:
    @pytest.mark.parametrize("name", sorted(DISTRIBUTIONS))
    def test_each_distribution_can_drive_a_spike_stimulus(self, name, circuit, tmp_path):
        config = _distribution_driven_config(circuit, DISTRIBUTIONS[name].model_copy(deep=True))

        result = generate(config, tmp_path)

        spike_file = result.directory / "Spikes_spikes.h5"
        assert spike_file.exists()
        with h5py.File(spike_file, "r") as handle:
            timestamps = np.array(handle[f"spikes/{VIRTUAL_POPULATION}/timestamps"])
        assert np.all(timestamps >= 0.0)

    def test_a_constant_interval_produces_regularly_spaced_spikes(self, circuit, tmp_path):
        """A constant inter-spike interval is the one case with a predictable spike train."""
        config = _distribution_driven_config(circuit, obi.FloatConstantDistribution(value=10.0))

        result = generate(config, tmp_path)

        with h5py.File(result.directory / "Spikes_spikes.h5", "r") as handle:
            node_ids = np.array(handle[f"spikes/{VIRTUAL_POPULATION}/node_ids"])
            timestamps = np.array(handle[f"spikes/{VIRTUAL_POPULATION}/timestamps"])

        for node_id in np.unique(node_ids):
            spikes = np.sort(timestamps[node_ids == node_id])
            intervals = np.diff(spikes)
            assert np.allclose(intervals, 10.0)

    def test_an_unused_distribution_changes_nothing(self, circuit_config, tmp_path):
        config = circuit_config(blocks={"Unused": obi.ExponentialDistribution(scale=10.0)})

        result = generate(config, tmp_path)

        assert result.inputs == {}
        assert "Unused" not in result.node_sets

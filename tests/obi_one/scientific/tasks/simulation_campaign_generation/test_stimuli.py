"""How stimulus blocks become the ``inputs`` section of the generated SONATA config.

The task dispatches on three different stimulus shapes -- spike stimuli, the Brian2 direct
Poisson stimulus, and everything else -- each with its own ``config()`` signature. These tests
cover every stimulus type reachable from a simulation config, plus the timestamp expansion and
targeting rules that apply across them.
"""

import h5py
import numpy as np
import pytest

import obi_one as obi
from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
    PointPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.population import VirtualPopulationNeuronSet
from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.stimuli import (
    Brian2CircuitStimulusUnion,
    CircuitStimulusUnion,
    IonChannelModelStimulusUnion,
    LearningEngineCircuitStimulusUnion,
    MEModelStimulusUnion,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    BIOPHYSICAL_POPULATION,
    DEFAULT_BIOPHYSICAL_NODE_SET,
    DEFAULT_POINT_NODE_SET,
    POINT_POPULATION,
    VIRTUAL_POPULATION,
    build_config,
    generate,
    union_member_names,
)

# Every continuous stimulus in CircuitStimulusUnion, with the SONATA module and input type it is
# expected to emit. A refactor that reroutes a stimulus through the wrong branch shows up here.
CONTINUOUS_STIMULI = {
    "ConstantCurrentClampSomaticStimulus": ("linear", "current_clamp"),
    "HyperpolarizingCurrentClampSomaticStimulus": ("hyperpolarizing", "current_clamp"),
    "LinearCurrentClampSomaticStimulus": ("linear", "current_clamp"),
    "MultiPulseCurrentClampSomaticStimulus": ("pulse", "current_clamp"),
    "NormallyDistributedCurrentClampSomaticStimulus": ("noise", "current_clamp"),
    "SinusoidalCurrentClampSomaticStimulus": ("sinusoidal", "current_clamp"),
    "RelativeConstantCurrentClampSomaticStimulus": ("relative_linear", "current_clamp"),
    "RelativeLinearCurrentClampSomaticStimulus": ("relative_linear", "current_clamp"),
    "RelativeNormallyDistributedCurrentClampSomaticStimulus": ("noise", "current_clamp"),
    "SubthresholdCurrentClampSomaticStimulus": ("subthreshold", "current_clamp"),
    "OrnsteinUhlenbeckCurrentSomaticStimulus": ("ornstein_uhlenbeck", "current_clamp"),
    "OrnsteinUhlenbeckConductanceSomaticStimulus": ("ornstein_uhlenbeck", "conductance"),
    "RelativeOrnsteinUhlenbeckCurrentSomaticStimulus": (
        "relative_ornstein_uhlenbeck",
        "current_clamp",
    ),
    "RelativeOrnsteinUhlenbeckConductanceSomaticStimulus": (
        "relative_ornstein_uhlenbeck",
        "conductance",
    ),
    "SpatiallyUniformElectricFieldStimulus": (
        "spatially_uniform_e_field",
        "extracellular_stimulation",
    ),
    "TemporallyCosineSpatiallyUniformElectricFieldStimulus": (
        "spatially_uniform_e_field",
        "extracellular_stimulation",
    ),
}

# Spike stimuli all emit a synapse_replay input backed by a generated HDF5 file.
SPIKE_STIMULI = [
    "PoissonSpikeStimulus",
    "FullySynchronousSpikeStimulus",
    "SinusoidalPoissonSpikeStimulus",
    "InterSpikeIntervalDistributionSpikeStimulus",
    "SpikeTimeDistributionSpikeStimulus",
]

# The two distribution-driven spike stimuli need a distribution block to point at.
NEEDS_DISTRIBUTION = {
    "InterSpikeIntervalDistributionSpikeStimulus",
    "SpikeTimeDistributionSpikeStimulus",
}


class TestUnionCoverage:
    def test_every_circuit_stimulus_is_exercised(self):
        covered = set(CONTINUOUS_STIMULI) | set(SPIKE_STIMULI)

        assert union_member_names(CircuitStimulusUnion) - covered == set()

    def test_me_model_and_learning_engine_stimuli_are_a_subset_of_the_circuit_ones(self):
        """Narrower unions reuse the same blocks, so the circuit coverage carries over."""
        assert union_member_names(MEModelStimulusUnion) <= set(CONTINUOUS_STIMULI)
        assert union_member_names(LearningEngineCircuitStimulusUnion) <= set(CONTINUOUS_STIMULI)

    def test_brian2_accepts_the_current_injections_the_poisson_kick_and_the_spike_replays(self):
        """The Brian2 runner turns `linear`, `pulse` and `sinusoidal` into current injections.

        It also understands `poisson` and `synapse_replay`. Its sinusoidal input has to be
        sampled on the simulation timestep, hence the dedicated block rather than
        `SinusoidalCurrentClampSomaticStimulus`.
        """
        assert union_member_names(Brian2CircuitStimulusUnion) == {
            "Brian2DirectPoissonStimulus",
            "ConstantCurrentClampSomaticStimulus",
            "LinearCurrentClampSomaticStimulus",
            "MultiPulseCurrentClampSomaticStimulus",
            "SimulationDtSinusoidalCurrentClampSomaticStimulus",
            *SPIKE_STIMULI,
        }

    def test_ion_channel_only_adds_the_voltage_clamps(self):
        """The SE clamps are reachable only from the ion channel config, which needs a database."""
        assert union_member_names(IonChannelModelStimulusUnion) - set(CONTINUOUS_STIMULI) == {
            "SEClampSomaticStimulus",
            "MultiLevelSEClampSomaticStimulus",
        }


class TestContinuousStimuli:
    @pytest.mark.parametrize(("name", "expected"), sorted(CONTINUOUS_STIMULI.items()))
    def test_module_and_input_type(self, name, expected, circuit, tmp_path):
        module, input_type = expected
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Stim": getattr(obi, name)()},
        )

        result = generate(config, tmp_path)

        assert result.inputs["Stim_0"]["module"] == module
        assert result.inputs["Stim_0"]["input_type"] == input_type

    @pytest.mark.parametrize("name", sorted(CONTINUOUS_STIMULI))
    def test_common_fields_are_always_present(self, name, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Stim": getattr(obi, name)()},
        )

        result = generate(config, tmp_path)

        entry = result.inputs["Stim_0"]
        assert entry["delay"] == pytest.approx(0.0)
        assert entry["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert entry["duration"] > 0.0

    def test_amplitude_reaches_the_generated_input(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Clamp": obi.ConstantCurrentClampSomaticStimulus(amplitude=0.42, duration=25.0)
            },
        )

        result = generate(config, tmp_path)

        assert result.inputs["Clamp_0"]["amp_start"] == pytest.approx(0.42)
        assert result.inputs["Clamp_0"]["duration"] == pytest.approx(25.0)

    def test_electric_field_emits_a_fields_list(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Field": obi.SpatiallyUniformElectricFieldStimulus(E_x=1.0, E_y=2.0, E_z=3.0)},
        )

        result = generate(config, tmp_path)

        assert result.inputs["Field_0"]["fields"] == [
            {"Ex": 1.0, "Ey": 2.0, "Ez": 3.0, "frequency": 0.0, "phase": 0.0}
        ]

    def test_several_stimuli_produce_independent_entries(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Depolarising": obi.ConstantCurrentClampSomaticStimulus(amplitude=0.5),
                "Hyperpolarising": obi.HyperpolarizingCurrentClampSomaticStimulus(),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.inputs) == {"Depolarising_0", "Hyperpolarising_0"}


class TestTimestampExpansion:
    def test_a_stimulus_without_timestamps_starts_at_zero(self, circuit, tmp_path):
        """The task supplies a default ``SingleTimestamp(start_time=0.0)``."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Clamp": obi.ConstantCurrentClampSomaticStimulus()},
        )

        result = generate(config, tmp_path)

        assert set(result.inputs) == {"Clamp_0"}
        assert result.inputs["Clamp_0"]["delay"] == pytest.approx(0.0)

    def test_a_single_timestamp_produces_one_entry(self, circuit, tmp_path):
        timestamps = obi.SingleTimestamp(start_time=30.0)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Start": timestamps,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(timestamps=timestamps.ref),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.inputs) == {"Clamp_0"}
        assert result.inputs["Clamp_0"]["delay"] == pytest.approx(30.0)

    def test_regular_timestamps_produce_one_entry_per_repetition(self, circuit, tmp_path):
        timestamps = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=3, interval=20.0)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Repeats": timestamps,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    timestamps=timestamps.ref, duration=5.0
                ),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.inputs) == {"Clamp_0", "Clamp_1", "Clamp_2"}
        assert [result.inputs[f"Clamp_{i}"]["delay"] for i in range(3)] == [0.0, 20.0, 40.0]

    def test_timestamp_offset_shifts_every_entry(self, circuit, tmp_path):
        timestamps = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=2, interval=20.0)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Repeats": timestamps,
                "Clamp": lambda: obi.ConstantCurrentClampSomaticStimulus(
                    timestamps=timestamps.ref, timestamp_offset=5.0, duration=5.0
                ),
            },
        )

        result = generate(config, tmp_path)

        assert [result.inputs[f"Clamp_{i}"]["delay"] for i in range(2)] == [5.0, 25.0]


class TestSpikeStimuli:
    @staticmethod
    def _spike_config(circuit, name, *, source=None, target=None):
        source_set = source or VirtualPopulationIDNeuronSet(
            population=VIRTUAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="source", elements=list(range(20))),
        )
        blocks: dict = {"Source": source_set}
        if target is not None:
            blocks["Target"] = target

        stimulus_class = getattr(obi, name)
        distribution = obi.ExponentialDistribution(scale=50.0)
        if name in NEEDS_DISTRIBUTION:
            blocks["Distribution"] = distribution

        def _stimulus():
            kwargs = {"source_neuron_set": source_set.ref}
            if target is not None:
                kwargs["targeted_neuron_set"] = target.ref
            if name in NEEDS_DISTRIBUTION:
                kwargs["distribution"] = distribution.ref
            return stimulus_class(**kwargs)

        blocks["Spikes"] = _stimulus
        return build_config(CircuitSimulationSingleConfig, circuit=circuit, blocks=blocks)

    @pytest.mark.parametrize("name", SPIKE_STIMULI)
    def test_spike_stimulus_emits_a_synapse_replay_input(self, name, circuit, tmp_path):
        config = self._spike_config(circuit, name)

        result = generate(config, tmp_path)

        assert result.inputs["Spikes"] == {
            "delay": 0.0,
            "duration": 100.0,
            "node_set": DEFAULT_BIOPHYSICAL_NODE_SET,
            "module": "synapse_replay",
            "input_type": "spikes",
            "spike_file": "Spikes_spikes.h5",
        }

    @pytest.mark.parametrize("name", SPIKE_STIMULI)
    def test_spike_file_is_written_next_to_the_config(self, name, circuit, tmp_path):
        config = self._spike_config(circuit, name)

        result = generate(config, tmp_path)

        spike_file = result.directory / "Spikes_spikes.h5"
        assert spike_file.exists()
        with h5py.File(spike_file, "r") as handle:
            node_ids = np.array(handle[f"spikes/{VIRTUAL_POPULATION}/node_ids"])
            timestamps = np.array(handle[f"spikes/{VIRTUAL_POPULATION}/timestamps"])
        assert len(node_ids) == len(timestamps)
        assert np.all(np.isin(node_ids, np.arange(20)))

    def test_spike_input_key_is_not_suffixed_by_timestamp(self, circuit, tmp_path):
        """Unlike continuous stimuli, all repetitions go into one replay file and one entry."""
        timestamps = obi.RegularTimestamps(start_time=0.0, number_of_repetitions=3, interval=20.0)
        source = VirtualPopulationIDNeuronSet(
            population=VIRTUAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="source", elements=[0, 1, 2]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Repeats": timestamps,
                "Source": source,
                "Spikes": lambda: obi.PoissonSpikeStimulus(
                    timestamps=timestamps.ref, source_neuron_set=source.ref, duration=10.0
                ),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.inputs) == {"Spikes"}

    def test_spike_duration_covers_the_whole_simulation(self, circuit, tmp_path):
        config = self._spike_config(circuit, "PoissonSpikeStimulus")
        config.initialize.simulation_length = 750.0

        result = generate(config, tmp_path)

        assert result.inputs["Spikes"]["duration"] == pytest.approx(750.0)

    def test_explicit_target_is_used_as_the_node_set(self, circuit, tmp_path):
        target = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="target", elements=[0, 1]),
        )
        config = self._spike_config(circuit, "PoissonSpikeStimulus", target=target)

        result = generate(config, tmp_path)

        assert result.inputs["Spikes"]["node_set"] == "Target"

    def test_a_virtual_target_is_rejected(self, circuit, tmp_path):
        """Spikes are replayed onto real synapses, so the target cannot itself be virtual."""
        source = VirtualPopulationNeuronSet(population=VIRTUAL_POPULATION)
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Source": source,
                "Spikes": lambda: obi.PoissonSpikeStimulus(source_neuron_set=source.ref),
            },
        )
        # Point the target at the virtual source, which the stimulus must refuse.
        config.stimuli["Spikes"].targeted_neuron_set = config.neuron_sets["Source"].ref

        with pytest.raises(OBIONEError):
            generate(config, tmp_path)


class TestBrian2DirectPoissonStimulus:
    def test_untargeted_stimulus_uses_the_simulation_default(self, brian2_config, tmp_path):
        config = brian2_config(blocks={"DirectPoisson": Brian2DirectPoissonStimulus()})

        result = generate(config, tmp_path)

        assert result.inputs["DirectPoisson"]["node_set"] == DEFAULT_POINT_NODE_SET
        assert result.inputs["DirectPoisson"]["input_type"] == "spikes"
        assert result.inputs["DirectPoisson"]["module"] == "poisson"

    def test_targeted_stimulus_uses_its_own_neuron_set(self, point_circuit, tmp_path):
        target = PointPopulationIDNeuronSet(
            population=POINT_POPULATION,
            neuron_ids=obi.NamedTuple(name="target", elements=[2]),
        )
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={
                "Target": target,
                "DirectPoisson": lambda: Brian2DirectPoissonStimulus(neuron_set=target.ref),
            },
        )

        result = generate(config, tmp_path)

        assert result.inputs["DirectPoisson"]["node_set"] == "Target"

    def test_frequency_weight_and_duration_reach_the_input(self, brian2_config, tmp_path):
        """``frequency`` is published under the SONATA name ``rate``."""
        config = brian2_config(
            blocks={
                "DirectPoisson": Brian2DirectPoissonStimulus(
                    frequency=25.0, weight=0.3, duration=60.0
                )
            }
        )

        result = generate(config, tmp_path)

        assert result.inputs["DirectPoisson"] == {
            "input_type": "spikes",
            "module": "poisson",
            "node_set": DEFAULT_POINT_NODE_SET,
            "rate": 25.0,
            "weight": 0.3,
            "delay": 0.0,
            "duration": 60.0,
        }

    def test_a_circuit_without_a_point_population_is_refused(self, circuit, tmp_path):
        """`Brian2SimulationScanConfig.validate_circuit` refuses it before anything runs."""
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"DirectPoisson": Brian2DirectPoissonStimulus()},
        )

        with pytest.raises(OBIONEError, match="needs exactly one point node population"):
            generate(config, tmp_path)

    def test_the_stimulus_default_is_the_simulation_default(self, brian2_config, tmp_path):
        """Brian2 has one default neuron set, shared by every untargeted block."""
        config = brian2_config(blocks={"DirectPoisson": Brian2DirectPoissonStimulus()})

        result = generate(config, tmp_path)

        assert result.inputs["DirectPoisson"]["node_set"] == result.sonata_config["node_set"]

    def test_an_untargeted_stimulus_is_refused_when_the_default_is_too_large(
        self, point_circuit, tmp_path, monkeypatch
    ):
        """One `PoissonInput` is built per target neuron, so the target has to stay small.

        Inheriting the simulation-wide default puts an untargeted stimulus over that ceiling on
        any real circuit, and it has to name its own neuron set instead.
        """
        monkeypatch.setattr(Brian2DirectPoissonStimulus, "MAX_NEURONS", 2)
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={"DirectPoisson": Brian2DirectPoissonStimulus()},
        )

        with pytest.raises(ValueError, match="exceeds the maximum allowed"):
            generate(config, tmp_path)

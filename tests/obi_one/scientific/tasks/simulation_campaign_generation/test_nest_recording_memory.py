"""A NEST simulation refuses, at generation, recordings its job could not hold in memory.

Each soma report has its own NEST multimeter, sampled on the report's Timestep over its window,
and every sample is held until the run ends. Generation adds up the samples of all recordings and
refuses those over the limit, which is lowered here to a size the small test circuit can cross:
its population ``exc`` has 4 neurons, and 100 ms at a 0.1 ms Timestep is 1,000 frames.
"""

import pytest

from obi_one.core.exception import ConfigValidationError
from obi_one.core.tuple import NamedTuple
from obi_one.scientific.blocks.neuron_sets.id import PointPopulationIDNeuronSet
from obi_one.scientific.blocks.recordings.soma import (
    SimulationDtSomaVoltageRecording,
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.nest import nest_base
from obi_one.scientific.tasks.generate_simulations.config.nest.nest_circuit import (
    NestCircuitSimulationSingleConfig,
)

from tests.obi_one.scientific.library.simulation.nest._circuits import write_nest_circuit
from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    build_config,
    generate,
)

FRAMES = 1_000  # 100 ms at a 0.1 ms Timestep


@pytest.fixture
def nest_circuit(tmp_path):
    return Circuit(name="nest", path=str(write_nest_circuit(tmp_path / "circuit").circuit_config))


@pytest.fixture
def limit_of_one_neuron(monkeypatch):
    """Allow exactly one neuron's worth of 0.1 ms samples for a 100 ms simulation."""
    monkeypatch.setattr(nest_base, "MAX_NEST_RECORDED_SAMPLES", FRAMES)


def _neuron(node_id: int) -> PointPopulationIDNeuronSet:
    return PointPopulationIDNeuronSet(
        population="exc", neuron_ids=NamedTuple(name="neuron", elements=[node_id])
    )


@pytest.mark.usefixtures("limit_of_one_neuron")
class TestNestRecordingMemory:
    def test_an_untargeted_recording_over_the_limit_is_refused(self, nest_circuit, tmp_path):
        """An untargeted recording records every point neuron, here 4 x 1,000 samples."""
        config = build_config(
            NestCircuitSimulationSingleConfig,
            circuit=nest_circuit,
            blocks={"Voltage": SomaVoltageRecording(dt=0.1)},
        )

        with pytest.raises(ConfigValidationError) as error:
            generate(config, tmp_path / "out")

        message = str(error.value)
        assert "'Voltage' (4 neurons in 'Default: All Point Neurons' x 1,000 frames)" in message
        assert "4,000 samples" in message
        assert f"at most {FRAMES:,} samples" in message
        assert not (tmp_path / "out" / "0" / "simulation_config.json").exists()

    def test_a_recording_within_the_limit_is_generated(self, nest_circuit, tmp_path):
        neuron = _neuron(0)
        config = build_config(
            NestCircuitSimulationSingleConfig,
            circuit=nest_circuit,
            blocks={
                "Neuron": neuron,
                "Voltage": lambda: SomaVoltageRecording(neuron_set=neuron.ref, dt=0.1),
            },
        )

        result = generate(config, tmp_path / "out")

        assert result.reports["Voltage"]["cells"] == "Neuron"

    def test_recordings_of_the_same_neurons_are_added_up(self, nest_circuit, tmp_path):
        """Each recording has its own multimeter, so two of one neuron hold twice the samples."""
        neuron = _neuron(0)
        config = build_config(
            NestCircuitSimulationSingleConfig,
            circuit=nest_circuit,
            blocks={
                "Neuron": neuron,
                "First": lambda: SomaVoltageRecording(neuron_set=neuron.ref, dt=0.1),
                "Second": lambda: SomaVoltageRecording(neuron_set=neuron.ref, dt=0.1),
            },
        )

        with pytest.raises(ConfigValidationError, match="2,000 samples"):
            generate(config, tmp_path / "out")

    def test_a_time_window_counts_only_its_own_frames(self, nest_circuit, tmp_path):
        """Two neurons over a 50 ms window are 2 x 500 samples, within the limit."""
        pair = PointPopulationIDNeuronSet(
            population="exc", neuron_ids=NamedTuple(name="pair", elements=[0, 1])
        )
        config = build_config(
            NestCircuitSimulationSingleConfig,
            circuit=nest_circuit,
            blocks={
                "Pair": pair,
                "Window": lambda: TimeWindowSomaVoltageRecording(
                    neuron_set=pair.ref, dt=0.1, start_time=0.0, end_time=50.0
                ),
            },
        )

        result = generate(config, tmp_path / "out")

        assert set(result.reports) == {"Window"}

    def test_a_coarser_timestep_records_fewer_frames(self, nest_circuit, tmp_path):
        """Every point neuron at a 0.4 ms Timestep is 4 x 250 samples, within the limit."""
        config = build_config(
            NestCircuitSimulationSingleConfig,
            circuit=nest_circuit,
            blocks={"Voltage": SomaVoltageRecording(dt=0.4)},
        )

        result = generate(config, tmp_path / "out")

        assert result.reports["Voltage"]["dt"] == pytest.approx(0.4)

    def test_the_simulation_timestep_recording_is_counted_at_that_timestep(
        self, nest_circuit, tmp_path
    ):
        """One neuron at 0.025 ms is 4,000 frames, four times the 0.1 ms limit."""
        neuron = _neuron(0)
        config = build_config(
            NestCircuitSimulationSingleConfig,
            circuit=nest_circuit,
            blocks={
                "Neuron": neuron,
                "Voltage": lambda: SimulationDtSomaVoltageRecording(neuron_set=neuron.ref),
            },
        )

        with pytest.raises(ConfigValidationError, match="4,000 samples"):
            generate(config, tmp_path / "out")


def test_no_recordings_are_always_accepted(nest_circuit, tmp_path, monkeypatch):
    monkeypatch.setattr(nest_base, "MAX_NEST_RECORDED_SAMPLES", 0)
    config = build_config(NestCircuitSimulationSingleConfig, circuit=nest_circuit)

    result = generate(config, tmp_path / "out")

    assert result.reports == {}

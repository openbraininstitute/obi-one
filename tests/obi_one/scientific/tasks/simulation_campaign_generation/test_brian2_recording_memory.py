"""A Brian2 simulation refuses, at generation, recordings its job could not hold in memory.

``simulate_brian2`` records the union of every recording's neurons at every timestep of the run,
so an untargeted recording on a whole-brain circuit is killed for running out of memory once the
simulation has been launched. Generation counts what would be recorded and refuses instead.

The synthetic point circuit has 3 neurons and 100 ms at 0.025 ms is 4,000 timesteps, so the limit
is lowered to a size those numbers can cross.
"""

import pytest

import obi_one as obi
from obi_one.core.exception import OBIONEError
from obi_one.scientific.tasks.generate_simulations.config.brian2 import brian2_base
from obi_one.scientific.tasks.generate_simulations.config.brian2.brian2_circuit import (
    Brian2CircuitSimulationSingleConfig,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    POINT_POPULATION,
    build_config,
    generate,
)

TIMESTEPS = 4_000  # 100 ms at the Brian2 timestep of 0.025 ms


@pytest.fixture
def limit_of_one_neuron(monkeypatch):
    """Allow exactly one neuron's worth of samples for a 100 ms simulation."""
    monkeypatch.setattr(brian2_base, "MAX_BRIAN2_RECORDED_SAMPLES", TIMESTEPS)


def _neuron(node_id: int, name: str) -> obi.PointPopulationIDNeuronSet:
    return obi.PointPopulationIDNeuronSet(
        population=POINT_POPULATION,
        neuron_ids=obi.NamedTuple(name=name, elements=[node_id]),
    )


class TestBrian2RecordingMemory:
    @pytest.mark.usefixtures("limit_of_one_neuron")
    def test_an_untargeted_recording_over_the_limit_is_refused(self, point_circuit, tmp_path):
        """An untargeted recording records every neuron, here 3 x 4,000 samples."""
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={"Voltage": obi.SimulationDtSomaVoltageRecording()},
        )

        with pytest.raises(OBIONEError) as error:
            generate(config, tmp_path)

        message = str(error.value)
        assert "'Voltage' (3 neurons in 'Default: All Point Neurons')" in message
        assert "12,000 samples" in message
        assert f"at most {TIMESTEPS:,} samples" in message
        assert not (tmp_path / "0" / "simulation_config.json").exists()

    @pytest.mark.usefixtures("limit_of_one_neuron")
    def test_a_recording_within_the_limit_is_generated(self, point_circuit, tmp_path):
        neuron = _neuron(0, "neuron")
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={
                "Neuron": neuron,
                "Voltage": lambda: obi.SimulationDtSomaVoltageRecording(neuron_set=neuron.ref),
            },
        )

        result = generate(config, tmp_path)

        assert result.reports["Voltage"]["cells"] == "Neuron"

    @pytest.mark.usefixtures("limit_of_one_neuron")
    def test_recordings_of_the_same_neurons_are_counted_once(self, point_circuit, tmp_path):
        """The runner records the union of the recordings' neurons, not their sum."""
        neuron = _neuron(0, "neuron")
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={
                "Neuron": neuron,
                "Whole": lambda: obi.SimulationDtSomaVoltageRecording(neuron_set=neuron.ref),
                "Window": lambda: obi.SimulationDtTimeWindowSomaVoltageRecording(
                    neuron_set=neuron.ref, start_time=0.0, end_time=10.0
                ),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.reports) == {"Whole", "Window"}

    @pytest.mark.usefixtures("limit_of_one_neuron")
    def test_a_time_window_still_counts_the_whole_run(self, point_circuit, tmp_path):
        """A 10 ms window on two neurons is held for all 4,000 timesteps, not its own 400."""
        pair = obi.PointPopulationIDNeuronSet(
            population=POINT_POPULATION,
            neuron_ids=obi.NamedTuple(name="pair", elements=[0, 1]),
        )
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={
                "Pair": pair,
                "Window": lambda: obi.SimulationDtTimeWindowSomaVoltageRecording(
                    neuron_set=pair.ref, start_time=0.0, end_time=10.0
                ),
            },
        )

        with pytest.raises(OBIONEError, match="8,000 samples"):
            generate(config, tmp_path)

    @pytest.mark.usefixtures("limit_of_one_neuron")
    def test_the_count_follows_the_simulation_length(self, point_circuit, tmp_path):
        """One neuron fits in 100 ms; the same neuron for 200 ms is twice the samples."""
        neuron = _neuron(0, "neuron")
        config = build_config(
            Brian2CircuitSimulationSingleConfig,
            circuit=point_circuit,
            blocks={
                "Neuron": neuron,
                "Voltage": lambda: obi.SimulationDtSomaVoltageRecording(neuron_set=neuron.ref),
            },
            initialize={"simulation_length": 200.0},
        )

        with pytest.raises(OBIONEError, match="8,000 samples"):
            generate(config, tmp_path)

    def test_no_recordings_are_always_accepted(self, point_circuit, tmp_path, monkeypatch):
        monkeypatch.setattr(brian2_base, "MAX_BRIAN2_RECORDED_SAMPLES", 0)
        config = build_config(Brian2CircuitSimulationSingleConfig, circuit=point_circuit)

        result = generate(config, tmp_path)

        assert result.reports == {}

    def test_the_default_limit_admits_a_whole_flywire_brain_for_a_millisecond(self):
        """Sanity check of the real limit against FlyWire v783's 138,639 neurons."""
        one_millisecond = 138_639 * 40
        assert one_millisecond < brian2_base.MAX_BRIAN2_RECORDED_SAMPLES
        # ...but not the 100 ms recording that was killed for running out of memory on staging.
        assert 138_639 * TIMESTEPS > brian2_base.MAX_BRIAN2_RECORDED_SAMPLES

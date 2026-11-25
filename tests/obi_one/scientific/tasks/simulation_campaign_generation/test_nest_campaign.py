"""The NEST campaign config generates what the NEST runner accepts, and refuses what it would not.

The NEST runner (``obi_one/scientific/library/simulation/nest/simulate_nest.py``) simulates
``nest_point`` populations and replays spikes from ``virtual`` ones. It accepts `linear`, `pulse`,
`sinusoidal` and `synapse_replay` inputs, soma voltage reports sampled every whole number of
steps, and connection overrides timed on a step. The circuit is the small SONATA-extension
circuit the runner's own tests build: population ``exc`` (4 ``nest_point`` neurons) and population
``input`` (2 ``virtual`` neurons), whose edges reach ``exc`` neurons 0 and 2.
"""

import re
from pathlib import Path
from unittest.mock import MagicMock

import libsonata
import numpy as np
import pytest

from obi_one.core.exception import ConfigValidationError
from obi_one.scientific.blocks.neuron_sets.base import NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.population import PointPopulationNeuronSet
from obi_one.scientific.blocks.neuron_sets.specific import AllVirtualNeurons
from obi_one.scientific.blocks.recordings.soma import (
    SimulationDtSomaVoltageRecording,
    SomaVoltageRecording,
    TimeWindowSomaVoltageRecording,
)
from obi_one.scientific.blocks.stimuli.spike.fully_synchronous import FullySynchronousSpikeStimulus
from obi_one.scientific.blocks.stimuli.spike.poisson import PoissonSpikeStimulus
from obi_one.scientific.blocks.stimuli.stimulus import (
    ConstantCurrentClampSomaticStimulus,
    LinearCurrentClampSomaticStimulus,
    MultiPulseCurrentClampSomaticStimulus,
    SimulationDtSinusoidalCurrentClampSomaticStimulus,
)
from obi_one.scientific.blocks.synaptic_manipulations.connect_disconnect import (
    DisconnectSynapticManipulation,
    ScaleWeightSynapticManipulation,
)
from obi_one.scientific.blocks.timestamps.regular import RegularTimestamps
from obi_one.scientific.blocks.timestamps.single import SingleTimestamp
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.tasks.generate_simulations.config.nest.nest_circuit import (
    NestCircuitSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    NestSimulationNeuronSetUnion,
)

from tests.obi_one.scientific.library.simulation.nest._circuits import (
    read_soma_report,
    write_nest_circuit,
)
from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    build_config,
    generate,
    union_member_names,
)

POINT_DEFAULT = "Default: All Point Neurons"
VIRTUAL_DEFAULT = "Default: All Virtual Neurons"
SIMULATION_LENGTH = 100.0


@pytest.fixture
def nest_circuit(tmp_path):
    """The runner tests' NEST circuit, with input synapses strong enough to make exc 0 fire."""
    paths = write_nest_circuit(tmp_path / "circuit", input_weight=1000.0)
    return Circuit(name="nest", path=str(paths.circuit_config))


def nest_config(circuit: Circuit, **kwargs):
    return build_config(NestCircuitSimulationSingleConfig, circuit=circuit, **kwargs)


def spike_times(directory: Path) -> list[float]:
    spikes = libsonata.SpikeReader(str(directory / "output" / "spikes.h5"))["exc"].get()
    return [time for _, time in spikes]


def run_in_nest(directory: Path) -> None:
    simulate_nest = pytest.importorskip("obi_one.scientific.library.simulation.nest.simulate_nest")
    simulate_nest.run_simulation(directory / "simulation_config.json", num_threads=1)


class TestOfferedNeuronSets:
    def test_point_and_virtual_sets_are_offered(self):
        """Spikes are replayed from the virtual populations, so they can be named as sources."""
        members = union_member_names(NestSimulationNeuronSetUnion)

        assert "AllPointNeurons" in members
        assert "AllVirtualNeurons" in members
        assert "VirtualPopulationNeuronSet" in members
        assert "AllBiophysicalNeurons" not in members


class TestCircuitValidation:
    def test_a_nest_circuit_is_accepted(self, nest_circuit, tmp_path):
        result = generate(nest_config(nest_circuit), tmp_path / "out")

        assert result.sonata_config["target_simulator"] == "NEST"
        assert result.sonata_config["run"]["dt"] == pytest.approx(0.025)

    def test_a_biophysical_circuit_is_refused(self, circuit, tmp_path):
        with pytest.raises(ConfigValidationError, match="'nest_point' and 'virtual'"):
            generate(nest_config(circuit), tmp_path)

    def test_a_brian2_circuit_is_refused(self, point_circuit, tmp_path):
        with pytest.raises(ConfigValidationError, match="'brian2_point'"):
            generate(nest_config(point_circuit), tmp_path)


class TestDefaultNeuronSets:
    def test_untargeted_blocks_use_all_point_neurons(self, nest_circuit, tmp_path):
        config = nest_config(
            nest_circuit,
            blocks={
                "Clamp": ConstantCurrentClampSomaticStimulus(duration=10.0),
                "Voltage": SomaVoltageRecording(),
                "Disconnect": DisconnectSynapticManipulation(),
            },
        )

        result = generate(config, tmp_path / "out")

        assert result.sonata_config["node_set"] == POINT_DEFAULT
        assert result.inputs["Clamp_0"]["node_set"] == POINT_DEFAULT
        assert result.reports["Voltage"]["cells"] == POINT_DEFAULT
        (override,) = result.sonata_config["connection_overrides"]
        assert override["source"] == override["target"] == POINT_DEFAULT

    def test_an_untargeted_spike_stimulus_replays_from_the_virtual_neurons(
        self, nest_circuit, tmp_path
    ):
        """The projections of a simplified circuit are silent unless spikes are replayed."""
        config = nest_config(nest_circuit, blocks={"Replay": PoissonSpikeStimulus(duration=50.0)})

        result = generate(config, tmp_path / "out")

        replay = result.inputs["Replay"]
        assert replay["module"] == "synapse_replay"
        assert replay["node_set"] == POINT_DEFAULT
        assert VIRTUAL_DEFAULT in result.node_sets
        spike_file = libsonata.SpikeReader(str(result.directory / replay["spike_file"]))
        assert spike_file.get_population_names() == ["input"]

    def test_the_point_neurons_stay_the_source_when_a_virtual_population_projects_nowhere(self):
        """A virtual population without edges onto a point population cannot be replayed."""
        nodes = {"exc": MagicMock(type="nest_point"), "input": MagicMock(type="virtual")}
        circuit = MagicMock()
        circuit.sonata_circuit.nodes.population_names = list(nodes)
        circuit.sonata_circuit.nodes.__getitem__.side_effect = nodes.__getitem__
        circuit.sonata_circuit.edges.population_names = []
        config = NestCircuitSimulationSingleConfig.empty_config()

        assert config.default_spike_source_population_type(circuit) is None

        edge = MagicMock()
        edge.source.name = "input"
        edge.target.type = "nest_point"
        circuit.sonata_circuit.edges.population_names = ["input__exc"]
        circuit.sonata_circuit.edges.__getitem__.side_effect = {"input__exc": edge}.__getitem__

        assert config.default_spike_source_population_type(circuit) == (
            NeuronSetPopulationType.VIRTUAL
        )


class TestRefusedAtGeneration:
    """What the runner would refuse once launched is refused before anything is written."""

    def test_a_recording_timestep_that_is_not_a_multiple_of_the_simulation_one(
        self, nest_circuit, tmp_path
    ):
        config = nest_config(nest_circuit, blocks={"Voltage": SomaVoltageRecording(dt=0.03)})

        with pytest.raises(
            ConfigValidationError, match=re.escape("must be a multiple of 0.025 ms")
        ):
            generate(config, tmp_path / "out")

    def test_a_manipulation_between_two_steps(self, nest_circuit, tmp_path):
        at = SingleTimestamp(start_time=10.01)
        config = nest_config(
            nest_circuit,
            blocks={
                "At": at,
                "Disconnect": lambda: DisconnectSynapticManipulation(timestamps=at.ref),
            },
        )

        with pytest.raises(ConfigValidationError, match=re.escape("is not a multiple of 0.025 ms")):
            generate(config, tmp_path / "out")
        assert not (tmp_path / "out" / "0" / "simulation_config.json").exists()

    def test_a_pulse_longer_than_its_period(self, nest_circuit, tmp_path):
        config = nest_config(
            nest_circuit,
            blocks={
                "Pulse": MultiPulseCurrentClampSomaticStimulus(
                    width=30.0, frequency=50.0, duration=50.0
                )
            },
        )

        with pytest.raises(
            ConfigValidationError, match=re.escape("Stimulus 'Pulse_0': A pulse of 30.0 ms")
        ):
            generate(config, tmp_path / "out")

    def test_a_current_clamp_on_no_point_neuron(self, nest_circuit, tmp_path):
        nobody = PointPopulationNeuronSet(population="exc", sample_percentage=0.0)
        config = nest_config(
            nest_circuit,
            blocks={
                "Nobody": nobody,
                "Clamp": lambda: ConstantCurrentClampSomaticStimulus(
                    neuron_set=nobody.ref, duration=10.0
                ),
            },
        )

        with pytest.raises(ConfigValidationError, match="contains no 'nest_point' neuron"):
            generate(config, tmp_path / "out")


class TestRunsInNest:
    """The generated config is accepted end-to-end by the NEST runner itself."""

    @staticmethod
    def _generate(circuit: Circuit, tmp_path: Path, *, disconnect_from: float | None = None):
        ticks = RegularTimestamps(start_time=10.0, number_of_repetitions=8, interval=10.0)
        blocks = {
            "Ticks": ticks,
            "Replay": lambda: FullySynchronousSpikeStimulus(timestamps=ticks.ref),
            "Ramp": LinearCurrentClampSomaticStimulus(
                amplitude_start=0.0, amplitude_end=0.0, duration=10.0
            ),
            "Pulse": MultiPulseCurrentClampSomaticStimulus(amplitude=0.0, duration=10.0),
            "Sine": SimulationDtSinusoidalCurrentClampSomaticStimulus(
                maximum_amplitude=0.0, duration=10.0
            ),
            "Voltage": SomaVoltageRecording(dt=0.1),
            "VoltageStep": SimulationDtSomaVoltageRecording(),
            "Window": TimeWindowSomaVoltageRecording(dt=0.5, start_time=20.0, end_time=60.0),
            "Scale": ScaleWeightSynapticManipulation(weight_scaling=1.0),
        }
        if disconnect_from is not None:
            at = SingleTimestamp(start_time=disconnect_from)
            inputs = AllVirtualNeurons()
            blocks["At"] = at
            blocks["Inputs"] = inputs
            blocks["Disconnect"] = lambda: DisconnectSynapticManipulation(
                presynaptic_neuron_set=inputs.ref, timestamps=at.ref
            )
        config = nest_config(
            circuit, blocks=blocks, initialize={"simulation_length": SIMULATION_LENGTH}
        )
        result = generate(config, tmp_path)
        run_in_nest(result.directory)
        return result

    def test_every_block_reaches_the_runner(self, nest_circuit, tmp_path):
        result = self._generate(nest_circuit, tmp_path / "all")

        modules = {name: entry["module"] for name, entry in result.inputs.items()}
        assert modules == {
            "Replay": "synapse_replay",
            "Ramp_0": "linear",
            "Pulse_0": "pulse",
            "Sine_0": "sinusoidal",
        }
        # The replayed volleys reach exc 0 through the input edges and make it fire.
        assert spike_times(result.directory)

    def test_reports_keep_their_own_timestep_and_window(self, nest_circuit, tmp_path):
        result = self._generate(nest_circuit, tmp_path / "reports")
        output = result.directory / "output"

        node_ids, times, data = read_soma_report(output / "Voltage.h5", "exc")
        assert list(node_ids) == [0, 1, 2, 3]
        assert np.allclose(np.diff(times), 0.1)
        assert data.shape == (len(times), 4)

        _, step_times, _ = read_soma_report(output / "VoltageStep.h5", "exc")
        assert np.allclose(np.diff(step_times), 0.025)

        _, window_times, _ = read_soma_report(output / "Window.h5", "exc")
        assert window_times[0] == pytest.approx(20.0)
        assert window_times[-1] < 60.0
        assert np.allclose(np.diff(window_times), 0.5)

    def test_a_disconnect_silences_the_replay_from_its_time(self, nest_circuit, tmp_path):
        """Cutting the input edges at 45 ms stops the firing the replay drives after it.

        The input synapses have a 2 ms delay, so no replayed volley arrives after 47 ms.
        """
        full = spike_times(self._generate(nest_circuit, tmp_path / "full").directory)
        cut = spike_times(
            self._generate(nest_circuit, tmp_path / "cut", disconnect_from=45.0).directory
        )

        assert any(time > 50.0 for time in full)
        assert cut
        assert all(time < 50.0 for time in cut)

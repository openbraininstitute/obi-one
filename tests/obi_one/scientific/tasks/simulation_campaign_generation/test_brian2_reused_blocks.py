"""The Brian2 campaign config reuses the shared stimulus, recording and manipulation blocks.

The Brian2 runner (``obi_one/scientific/library/simulation/brian2/simulate_brian2.py``) only
accepts a subset of SONATA: current injections via `linear`/`pulse`/`sinusoidal`, a direct
`poisson` membrane kick, soma voltage reports sampled on the integration timestep, and
connection overrides carrying `weight`/`synapse_delay_override`. These tests pin the blocks the
config offers to that subset, and run a generated config through the real runner to prove it.
"""

import json
from pathlib import Path
from typing import get_args

import pytest

import obi_one as obi
import obi_one.scientific.library.simulation.brian2.simulate_brian2 as brian2_runner
from obi_one.scientific.blocks.stimuli.brian2_poisson import Brian2DirectPoissonStimulus
from obi_one.scientific.unions_and_references.manipulations import (
    Brian2SynapticManipulationsUnion,
)
from obi_one.scientific.unions_and_references.recordings import Brian2RecordingUnion
from obi_one.scientific.unions_and_references.stimuli import Brian2CircuitStimulusUnion

# The synthetic FlyWire-style point circuit: one `brian2_point` population `drosophila` (3
# neurons), with a `sugar` node set covering neurons 0 and 1.
CIRCUIT_CONFIG = (
    Path(__file__).parents[2] / "library" / "simulation" / "data" / "circuit_config.json"
)

SIMULATION_LENGTH = 5.0


def _union_members(union) -> set[str]:
    return {member.__name__ for member in get_args(get_args(union)[0])}


def _generate(tmp_path: Path) -> dict:
    """Generate a Brian2 campaign using one of every reusable block; return the SONATA config."""
    sim_conf = obi.Brian2CircuitSimulationScanConfig.empty_config()
    sim_conf.set(obi.Info(campaign_name="T", campaign_description="T"), name="info")

    neuron_set = obi.PointPopulationPredefinedNeuronSet(node_set="sugar", population="drosophila")
    sim_conf.add(neuron_set, name="Sugar")

    timestamps = obi.SingleTimestamp(start_time=0.0)
    sim_conf.add(timestamps, name="Start")

    sim_conf.add(Brian2DirectPoissonStimulus(neuron_set=neuron_set.ref), name="Poisson")
    sim_conf.add(
        obi.ConstantCurrentClampSomaticStimulus(
            neuron_set=neuron_set.ref, timestamps=timestamps.ref, amplitude=12000.0, duration=4.0
        ),
        name="Constant",
    )
    sim_conf.add(
        obi.LinearCurrentClampSomaticStimulus(
            neuron_set=neuron_set.ref, timestamps=timestamps.ref, duration=4.0
        ),
        name="Ramp",
    )
    sim_conf.add(
        obi.MultiPulseCurrentClampSomaticStimulus(
            neuron_set=neuron_set.ref, timestamps=timestamps.ref, duration=4.0
        ),
        name="Pulse",
    )
    sim_conf.add(
        obi.Brian2SinusoidalCurrentClampSomaticStimulus(
            neuron_set=neuron_set.ref, timestamps=timestamps.ref, duration=4.0
        ),
        name="Sine",
    )

    sim_conf.add(obi.Brian2SomaVoltageRecording(neuron_set=neuron_set.ref), name="Voltage")
    sim_conf.add(
        obi.Brian2TimeWindowSomaVoltageRecording(
            neuron_set=neuron_set.ref, start_time=0.0, end_time=SIMULATION_LENGTH
        ),
        name="VoltageWindow",
    )

    sim_conf.add(
        obi.DisconnectSynapticManipulation(
            presynaptic_neuron_set=neuron_set.ref,
            postsynaptic_neuron_set=neuron_set.ref,
            timestamps=timestamps.ref,
        ),
        name="Disconnect",
    )

    sim_conf.set(
        obi.Brian2CircuitSimulationScanConfig.Initialize(
            circuit=obi.Circuit(name="drosophila", path=str(CIRCUIT_CONFIG)),
            simulation_length=SIMULATION_LENGTH,
        ),
        name="initialize",
    )

    scan = obi.GridScanGenerationTask(
        form=sim_conf.validated_config(),
        output_root=tmp_path / "scan",
        coordinate_directory_option="ZERO_INDEX",
    )
    scan.execute()
    obi.run_tasks_for_generated_scan(scan)

    return json.loads((tmp_path / "scan" / "0" / "simulation_config.json").read_text())


@pytest.fixture(scope="module")
def sonata_config(tmp_path_factory) -> dict:
    return _generate(tmp_path_factory.mktemp("brian2_blocks"))


class TestOfferedBlocks:
    """Only blocks the runner can execute are offered by the Brian2 config."""

    def test_stimuli_are_the_runner_supported_modules(self):
        assert _union_members(Brian2CircuitStimulusUnion) == {
            "Brian2DirectPoissonStimulus",
            "ConstantCurrentClampSomaticStimulus",
            "LinearCurrentClampSomaticStimulus",
            "MultiPulseCurrentClampSomaticStimulus",
            "Brian2SinusoidalCurrentClampSomaticStimulus",
        }

    def test_synaptic_manipulations_exclude_synapse_configure_and_modoverride(self):
        # `SynapticMgManipulation` and `ScaleAcetylcholineUSESynapticManipulation` emit
        # `modoverride`/`synapse_configure`, on which the runner raises outright.
        assert _union_members(Brian2SynapticManipulationsUnion) == {
            "ConnectSynapticManipulation",
            "DisconnectSynapticManipulation",
        }

    def test_recordings_have_no_timestep_of_their_own(self):
        for recording in get_args(get_args(Brian2RecordingUnion)[0]):
            assert "dt" not in recording.model_fields, recording.__name__

    def test_neuron_recordings_keep_their_timestep(self):
        # The split that gave Brian2 its dt-less recordings must not have taken `dt` away from
        # the recordings every other simulator uses.
        assert "dt" in obi.SomaVoltageRecording.model_fields
        assert "dt" in obi.TimeWindowSomaVoltageRecording.model_fields
        assert "dt" in obi.SinusoidalCurrentClampSomaticStimulus.model_fields


class TestGeneratedConfig:
    """Every reused block reaches the generated SONATA config in a form the runner accepts."""

    def test_every_stimulus_is_emitted_with_a_supported_module(self, sonata_config):
        modules = {name: entry["module"] for name, entry in sonata_config["inputs"].items()}
        assert modules == {
            "Poisson": "poisson",
            "Constant_0": "linear",
            "Ramp_0": "linear",
            "Pulse_0": "pulse",
            "Sine_0": "sinusoidal",
        }

    def test_reports_are_sampled_on_the_simulation_timestep(self, sonata_config):
        # `_get_reports` raises on any report whose dt differs from `run.dt`, which is why the
        # Brian2 recordings do not expose a Timestep.
        assert set(sonata_config["reports"]) == {"Voltage", "VoltageWindow"}
        for report in sonata_config["reports"].values():
            assert report["dt"] == sonata_config["run"]["dt"]

    def test_sinusoidal_signal_is_sampled_on_the_simulation_timestep(self, sonata_config):
        # `Sinusoidal._get_currents` asserts the input dt equals the simulation dt.
        assert sonata_config["inputs"]["Sine_0"]["dt"] == sonata_config["run"]["dt"]

    def test_time_window_recording_keeps_its_window(self, sonata_config):
        assert sonata_config["reports"]["VoltageWindow"]["end_time"] == SIMULATION_LENGTH

    def test_manipulation_becomes_a_supported_connection_override(self, sonata_config):
        (override,) = sonata_config["connection_overrides"]
        assert override["name"] == "Disconnect"
        assert override["weight"] == pytest.approx(0.0)
        for unsupported in (
            "spont_minis",
            "synapse_configure",
            "modoverride",
            "neuromodulation_dtc",
            "neuromodulation_strength",
        ):
            assert unsupported not in override


class TestUntargetedBlocks:
    """A block left without a target falls back to the simulation-wide default neuron set."""

    @staticmethod
    def _generate_untargeted(tmp_path: Path) -> dict:
        sim_conf = obi.Brian2CircuitSimulationScanConfig.empty_config()
        sim_conf.set(obi.Info(campaign_name="T", campaign_description="T"), name="info")

        sim_conf.add(Brian2DirectPoissonStimulus(), name="Poisson")
        sim_conf.add(
            obi.ConstantCurrentClampSomaticStimulus(amplitude=12000.0, duration=4.0),
            name="Constant",
        )
        sim_conf.add(obi.Brian2SomaVoltageRecording(), name="Voltage")
        sim_conf.add(obi.DisconnectSynapticManipulation(), name="Disconnect")

        sim_conf.set(
            obi.Brian2CircuitSimulationScanConfig.Initialize(
                circuit=obi.Circuit(name="drosophila", path=str(CIRCUIT_CONFIG)),
                simulation_length=SIMULATION_LENGTH,
            ),
            name="initialize",
        )

        scan = obi.GridScanGenerationTask(
            form=sim_conf.validated_config(),
            output_root=tmp_path / "scan",
            coordinate_directory_option="ZERO_INDEX",
        )
        scan.execute()
        obi.run_tasks_for_generated_scan(scan)

        return json.loads((tmp_path / "scan" / "0" / "simulation_config.json").read_text())

    def test_untargeted_blocks_use_the_simulation_default(self, tmp_path):
        sonata_config = self._generate_untargeted(tmp_path)
        simulation_default = "Default: All Point Neurons"

        # This is what makes the config's PointNeuronSetReference label the simulation default:
        # every reused block falls back to it...
        assert sonata_config["node_set"] == simulation_default
        assert sonata_config["inputs"]["Constant_0"]["node_set"] == simulation_default
        assert sonata_config["reports"]["Voltage"]["cells"] == simulation_default
        (override,) = sonata_config["connection_overrides"]
        assert override["source"] == override["target"] == simulation_default

        # ...except the Direct Poisson stimulus, which drives the smaller `sugar` set so that it
        # stays under the block's neuron limit.
        assert (
            sonata_config["inputs"]["Poisson"]["node_set"]
            == "Default: Sugar gustatory receptor neurons"
        )


class TestRunsInBrian2:
    """The generated config is accepted end-to-end by the Brian2 runner itself."""

    def test_generated_config_runs(self, tmp_path):
        _generate(tmp_path)
        net = brian2_runner.run_sonata_brian2_trial(
            tmp_path / "scan" / "0" / "simulation_config.json"
        )

        # The current injections drive the stimulated `sugar` neurons (0 and 1) to spike...
        spikes = dict(net.spike_monitor.spike_trains().items())
        assert len(spikes[0]) > 0
        assert len(spikes[1]) > 0

        # ...and the soma voltage report was recorded over the two of them.
        assert net.state_monitor is not None
        assert net.state_monitor.v.shape[0] == 2

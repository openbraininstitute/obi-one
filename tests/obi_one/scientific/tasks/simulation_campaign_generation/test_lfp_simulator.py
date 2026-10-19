"""The simulator a circuit simulation is generated for, and the blocks each one can run.

The simulator is the user's choice, NEURON by default. Neurodamus computes LFP reports only under
CoreNEURON, which cannot simulate the extracellular mechanism that electric field stimuli are
applied through, so each refuses the other's block.
"""

import pytest

from obi_one.core.exception import ConfigValidationError
from obi_one.scientific.blocks.recordings.extracellular import (
    ExtracellularElectrodeArrayRecordingBlock,
)
from obi_one.scientific.blocks.recordings.soma import SomaVoltageRecording
from obi_one.scientific.blocks.stimuli.electric_field import (
    SpatiallyUniformElectricFieldStimulus,
    TemporallyCosineSpatiallyUniformElectricFieldStimulus,
)
from obi_one.scientific.from_id.extracellular_recording_array_from_id import (
    SimulatableExtracellularRecordingArrayFromID,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    DEFAULT_BIOPHYSICAL_NODE_SET,
    FakeDBClient,
    build_config,
    generate,
)

ARRAY_ID = "9f8ac5a5-4b6c-4e57-9a2f-2e3f7d0b1c44"
ELECTRIC_FIELDS = [
    SpatiallyUniformElectricFieldStimulus,
    TemporallyCosineSpatiallyUniformElectricFieldStimulus,
]


def _lfp():
    return ExtracellularElectrodeArrayRecordingBlock(
        electrode_array=SimulatableExtracellularRecordingArrayFromID(id_str=ARRAY_ID)
    )


def _config(circuit, blocks, simulator=None):
    initialize = {"simulator": simulator} if simulator else None
    return build_config(
        CircuitSimulationSingleConfig, circuit=circuit, blocks=blocks, initialize=initialize
    )


class TestSimulator:
    def test_the_simulator_defaults_to_neuron(self, circuit, tmp_path):
        result = generate(_config(circuit, {"Soma": SomaVoltageRecording()}), tmp_path)

        assert result.sonata_config["target_simulator"] == "NEURON"

    def test_the_chosen_simulator_is_written(self, circuit, tmp_path):
        config = _config(circuit, {"Soma": SomaVoltageRecording()}, simulator="CORENEURON")

        result = generate(config, tmp_path)

        assert result.sonata_config["target_simulator"] == "CORENEURON"


class TestLFPRecordings:
    def test_run_under_coreneuron(self, circuit, tmp_path):
        result = generate(_config(circuit, {"LFP": _lfp()}, simulator="CORENEURON"), tmp_path)

        assert result.reports["LFP"]["type"] == "lfp"
        assert result.sonata_config["target_simulator"] == "CORENEURON"

    def test_are_refused_under_neuron(self, circuit, tmp_path):
        with pytest.raises(
            ConfigValidationError,
            match=r"LFP recordings \('LFP'\) need CoreNEURON: select it as the simulator",
        ):
            generate(_config(circuit, {"LFP": _lfp()}), tmp_path)

    def test_the_refusal_comes_before_anything_is_written(self, circuit, tmp_path):
        db_client = FakeDBClient()

        with pytest.raises(ConfigValidationError):
            generate(_config(circuit, {"LFP": _lfp()}), tmp_path, db_client=db_client)

        assert db_client.calls == []
        assert list((tmp_path / "0").iterdir()) == []

    def test_names_are_left_to_neurodamus(self, circuit, tmp_path):
        """CoreNEURON reads report names and targets split on whitespace; neurodamus handles it."""
        config = _config(
            circuit,
            {"Recording 0": SomaVoltageRecording(), "LFP A": _lfp()},
            simulator="CORENEURON",
        )

        result = generate(config, tmp_path)

        assert set(result.reports) == {"Recording 0", "LFP A"}
        assert {report["cells"] for report in result.reports.values()} == {
            DEFAULT_BIOPHYSICAL_NODE_SET
        }


class TestElectricFields:
    @pytest.mark.parametrize("field", ELECTRIC_FIELDS)
    def test_run_under_neuron(self, field, circuit, tmp_path):
        result = generate(_config(circuit, {"Field": field()}), tmp_path)

        assert result.sonata_config["target_simulator"] == "NEURON"

    @pytest.mark.parametrize("field", ELECTRIC_FIELDS)
    def test_are_refused_under_coreneuron(self, field, circuit, tmp_path):
        with pytest.raises(
            ConfigValidationError,
            match=r"Electric field stimuli \('Field'\) need NEURON",
        ):
            generate(_config(circuit, {"Field": field()}, simulator="CORENEURON"), tmp_path)

    @pytest.mark.parametrize("simulator", ["NEURON", "CORENEURON"])
    def test_neither_simulator_runs_them_with_lfp(self, simulator, circuit, tmp_path):
        config = _config(
            circuit,
            {"Field": SpatiallyUniformElectricFieldStimulus(), "LFP": _lfp()},
            simulator=simulator,
        )

        with pytest.raises(ConfigValidationError):
            generate(config, tmp_path)

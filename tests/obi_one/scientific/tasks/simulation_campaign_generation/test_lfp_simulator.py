"""What recording LFP changes about the simulation generated around it.

Neurodamus computes LFP reports only under CoreNEURON, which cannot simulate the extracellular
mechanism that electric field stimuli are applied through.
"""

import pytest

import obi_one as obi
from obi_one.core.exception import ConfigValidationError
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
    obi.SpatiallyUniformElectricFieldStimulus,
    obi.TemporallyCosineSpatiallyUniformElectricFieldStimulus,
]


def _lfp(**kwargs):
    return obi.ExtracellularElectrodeArrayRecordingBlock(
        electrode_array=obi.SimulatableExtracellularRecordingArrayFromID(id_str=ARRAY_ID), **kwargs
    )


def _config(circuit, blocks):
    return build_config(CircuitSimulationSingleConfig, circuit=circuit, blocks=blocks)


class TestSimulator:
    def test_a_simulation_recording_lfp_runs_under_coreneuron(self, circuit, tmp_path):
        result = generate(_config(circuit, {"LFP": _lfp()}), tmp_path)

        assert result.sonata_config["target_simulator"] == "CORENEURON"

    def test_one_without_lfp_stays_on_neuron(self, circuit, tmp_path):
        result = generate(_config(circuit, {"Soma": obi.SomaVoltageRecording()}), tmp_path)

        assert result.sonata_config["target_simulator"] == "NEURON"


class TestReportNames:
    def test_names_are_left_to_neurodamus(self, circuit, tmp_path):
        """CoreNEURON reads report names and targets split on whitespace; neurodamus handles it."""
        config = _config(circuit, {"Recording 0": obi.SomaVoltageRecording(), "LFP A": _lfp()})

        result = generate(config, tmp_path)

        assert set(result.reports) == {"Recording 0", "LFP A"}
        assert {report["cells"] for report in result.reports.values()} == {
            DEFAULT_BIOPHYSICAL_NODE_SET
        }


class TestElectricFields:
    """Electric fields need NEURON's extracellular mechanism, which CoreNEURON cannot simulate."""

    @pytest.mark.parametrize("field", ELECTRIC_FIELDS)
    def test_lfp_with_an_electric_field_is_refused(self, field, circuit, tmp_path):
        config = _config(circuit, {"Field": field(), "LFP": _lfp()})

        with pytest.raises(
            ConfigValidationError,
            match=r"LFP recordings \('LFP'\) cannot be combined with electric field stimuli "
            r"\('Field'\)",
        ):
            generate(config, tmp_path)

    def test_the_refusal_comes_before_anything_is_written(self, circuit, tmp_path):
        config = _config(
            circuit, {"Field": obi.SpatiallyUniformElectricFieldStimulus(), "LFP": _lfp()}
        )
        db_client = FakeDBClient()

        with pytest.raises(ConfigValidationError):
            generate(config, tmp_path, db_client=db_client)

        assert db_client.calls == []
        assert list((tmp_path / "0").iterdir()) == []

    def test_an_electric_field_alone_stays_on_neuron(self, circuit, tmp_path):
        config = _config(circuit, {"Field": obi.SpatiallyUniformElectricFieldStimulus()})

        result = generate(config, tmp_path)

        assert result.sonata_config["target_simulator"] == "NEURON"

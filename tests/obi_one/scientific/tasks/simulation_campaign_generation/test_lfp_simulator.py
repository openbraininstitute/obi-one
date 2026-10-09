"""What recording LFP changes about the simulation generated around it.

Neurodamus computes LFP reports only under CoreNEURON. CoreNEURON reads each report's name and
target from a whitespace-separated file (report.conf), and cannot simulate the extracellular
mechanism that electric field stimuli are applied through.
"""

import pytest

import obi_one as obi
from obi_one.core.exception import ConfigValidationError
from obi_one.scientific.blocks.neuron_sets.id import BiophysicalPopulationIDNeuronSet
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    BIOPHYSICAL_POPULATION,
    DEFAULT_BIOPHYSICAL_NODE_SET,
    MULTI_POPULATION_CIRCUIT_PATH,
    FakeDBClient,
    build_config,
    generate,
)

ARRAY_ID = "9f8ac5a5-4b6c-4e57-9a2f-2e3f7d0b1c44"
DEFAULT_ALIAS = "Default:_All_Biophysical_Neurons"
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
    """Under CoreNEURON, report names and report targets are written without whitespace."""

    def test_report_names_lose_their_whitespace(self, circuit, tmp_path):
        config = _config(
            circuit, {"Recording 0": obi.SomaVoltageRecording(), "Recording 1": _lfp()}
        )

        result = generate(config, tmp_path)

        assert set(result.reports) == {"Recording_0", "Recording_1"}

    def test_report_names_are_kept_under_neuron(self, circuit, tmp_path):
        result = generate(_config(circuit, {"Recording 0": obi.SomaVoltageRecording()}), tmp_path)

        assert set(result.reports) == {"Recording 0"}

    def test_a_target_with_whitespace_is_replaced_by_an_alias(self, circuit, tmp_path):
        config = _config(circuit, {"Soma": obi.SomaVoltageRecording(), "LFP": _lfp()})

        result = generate(config, tmp_path)

        assert {report["cells"] for report in result.reports.values()} == {DEFAULT_ALIAS}
        assert result.node_sets[DEFAULT_ALIAS] == [DEFAULT_BIOPHYSICAL_NODE_SET]
        assert result.dangling_node_sets() == set()

    def test_the_alias_selects_the_same_neurons(self, circuit, tmp_path):
        result = generate(_config(circuit, {"LFP": _lfp()}), tmp_path)

        def resolve(name):
            return result.resolved_node_set_ids(
                name, MULTI_POPULATION_CIRCUIT_PATH, BIOPHYSICAL_POPULATION
            )

        assert resolve(DEFAULT_ALIAS) == resolve(DEFAULT_BIOPHYSICAL_NODE_SET)
        assert len(resolve(DEFAULT_ALIAS)) > 0

    def test_a_target_without_whitespace_is_kept(self, circuit, tmp_path):
        target = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="target", elements=[0, 1]),
        )
        config = _config(circuit, {"Target": target, "LFP": lambda: _lfp(neuron_set=target.ref)})

        result = generate(config, tmp_path)

        assert result.reports["LFP"]["cells"] == "Target"
        assert DEFAULT_ALIAS not in result.node_sets

    def test_only_reports_are_retargeted(self, circuit, tmp_path):
        """report.conf is the only place CoreNEURON reads a name from."""
        config = _config(
            circuit,
            {"Clamp": obi.ConstantCurrentClampSomaticStimulus(amplitude=0.1), "LFP": _lfp()},
        )

        result = generate(config, tmp_path)

        assert result.sonata_config["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET
        assert result.inputs["Clamp_0"]["node_set"] == DEFAULT_BIOPHYSICAL_NODE_SET

    def test_a_compartment_set_target_is_aliased(self, morphology_circuit, tmp_path):
        locations = obi.RandomMorphologyLocations(random_seed=0, number_of_locations=2)
        config = _config(
            morphology_circuit,
            {
                "Apical Locations": locations,
                "Voltage": lambda: obi.MorphologyLocationVoltageRecording(
                    morphology_locations=locations.ref
                ),
                "LFP": _lfp(),
            },
        )

        result = generate(config, tmp_path)

        assert result.reports["Voltage"]["compartment_set"] == "Apical_Locations"
        assert (
            result.compartment_sets["Apical_Locations"]
            == result.compartment_sets["Apical Locations"]
        )

    def test_recordings_that_would_share_a_name_are_refused(self, circuit, tmp_path):
        config = _config(circuit, {"LFP A": _lfp(), "LFP_A": _lfp()})

        with pytest.raises(
            ConfigValidationError, match="'LFP A' and 'LFP_A' would both be named 'LFP_A'"
        ):
            generate(config, tmp_path)


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

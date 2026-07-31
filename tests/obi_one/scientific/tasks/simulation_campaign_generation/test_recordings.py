"""How recording blocks become the ``reports`` section of the generated SONATA config."""

import pytest

import obi_one as obi
from obi_one.core.exception import OBIONEError
from obi_one.scientific.blocks.neuron_sets.id import (
    BiophysicalPopulationIDNeuronSet,
    VirtualPopulationIDNeuronSet,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitSimulationSingleConfig,
)
from obi_one.scientific.unions_and_references.recordings import (
    IonChannelModelRecordingUnion,
    RecordingUnion,
)

from tests.obi_one.scientific.tasks.simulation_campaign_generation.conftest import (
    BIOPHYSICAL_POPULATION,
    DEFAULT_BIOPHYSICAL_NODE_SET,
    VIRTUAL_POPULATION,
    build_config,
    generate,
    union_member_names,
)

SOMA_REPORT_SHAPE = {
    "sections": "soma",
    "type": "compartment",
    "compartments": "center",
    "variable_name": "v",
    "unit": "mV",
}


class TestUnionCoverage:
    def test_every_recording_in_the_circuit_union_is_exercised(self):
        assert union_member_names(RecordingUnion) == {
            "SomaVoltageRecording",
            "TimeWindowSomaVoltageRecording",
        }

    def test_ion_channel_configs_add_a_variable_recording(self):
        """``IonChannelVariableRecording`` is reachable only from the database-backed config."""
        assert union_member_names(IonChannelModelRecordingUnion) - union_member_names(
            RecordingUnion
        ) == {"IonChannelVariableRecording"}


class TestSomaVoltageRecording:
    def test_report_shape(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Voltage": obi.SomaVoltageRecording()},
        )

        result = generate(config, tmp_path)

        assert result.reports["Voltage"] == {
            "cells": DEFAULT_BIOPHYSICAL_NODE_SET,
            **SOMA_REPORT_SHAPE,
            "dt": 0.1,
            "start_time": 0.0,
            "end_time": 100.0,
        }

    def test_end_time_follows_the_simulation_length(self, circuit, tmp_path):
        """A plain soma recording spans the whole simulation."""
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Voltage": obi.SomaVoltageRecording()},
            initialize={"simulation_length": 400.0},
        )

        result = generate(config, tmp_path)

        assert result.reports["Voltage"]["end_time"] == pytest.approx(400.0)

    def test_custom_timestep(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Voltage": obi.SomaVoltageRecording(dt=0.5)},
        )

        result = generate(config, tmp_path)

        assert result.reports["Voltage"]["dt"] == pytest.approx(0.5)

    def test_explicit_neuron_set_is_recorded_from(self, circuit, tmp_path):
        target = BiophysicalPopulationIDNeuronSet(
            population=BIOPHYSICAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="target", elements=[0, 1]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Target": target,
                "Voltage": lambda: obi.SomaVoltageRecording(neuron_set=target.ref),
            },
        )

        result = generate(config, tmp_path)

        assert result.reports["Voltage"]["cells"] == "Target"


class TestTimeWindowSomaVoltageRecording:
    def test_window_bounds_are_used_verbatim(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Window": obi.TimeWindowSomaVoltageRecording(start_time=20.0, end_time=60.0)},
        )

        result = generate(config, tmp_path)

        assert result.reports["Window"]["start_time"] == pytest.approx(20.0)
        assert result.reports["Window"]["end_time"] == pytest.approx(60.0)

    def test_window_does_not_extend_to_the_simulation_length(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Window": obi.TimeWindowSomaVoltageRecording(start_time=0.0, end_time=10.0)},
            initialize={"simulation_length": 500.0},
        )

        result = generate(config, tmp_path)

        assert result.reports["Window"]["end_time"] == pytest.approx(10.0)


class TestReportsSection:
    def test_several_recordings_produce_independent_reports(self, circuit, tmp_path):
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={
                "Whole run": obi.SomaVoltageRecording(),
                "First window": obi.TimeWindowSomaVoltageRecording(start_time=0.0, end_time=10.0),
            },
        )

        result = generate(config, tmp_path)

        assert set(result.reports) == {"Whole run", "First window"}

    def test_no_recordings_yields_an_empty_reports_section(self, circuit_config, tmp_path):
        result = generate(circuit_config(), tmp_path)

        assert result.reports == {}

    def test_a_config_without_a_recordings_field_still_gets_an_empty_section(
        self, brian2_config, tmp_path
    ):
        """Brian2 configs expose no recordings, but the SONATA key is still emitted."""
        config = brian2_config()
        assert not hasattr(config, "recordings")

        result = generate(config, tmp_path)

        assert result.reports == {}

    def test_recording_from_a_virtual_neuron_set_is_rejected(self, circuit, tmp_path):
        """There is nothing to record on a virtual population."""
        virtual = VirtualPopulationIDNeuronSet(
            population=VIRTUAL_POPULATION,
            neuron_ids=obi.NamedTuple(name="virtual", elements=[0, 1]),
        )
        config = build_config(
            CircuitSimulationSingleConfig,
            circuit=circuit,
            blocks={"Virtual": virtual, "Voltage": obi.SomaVoltageRecording()},
        )
        config.recordings["Voltage"].neuron_set = config.neuron_sets["Virtual"].ref

        with pytest.raises(OBIONEError, match="should be non-virtual"):
            generate(config, tmp_path)

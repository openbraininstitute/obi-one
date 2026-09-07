"""Tests for MEModel validation workflow."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from bluecellulab.simulation.neuron_globals import NeuronGlobals
from bluecellulab.validation import EfelMeasurement, GreaterThan, SequenceProtocol, StepProtocol
from bluecellulab.validation.base import TestResult

from obi_one.scientific.validations.memodel.config import (
    SimulatorConfig,
    extract_simulator_config_from_hoc,
    load_simulator_config_from_hoc,
)
from obi_one.scientific.validations.memodel.presets import spiking_preset
from obi_one.scientific.validations.memodel.profiles import (
    MEModelValidationProfile,
    ThalamicMEModelValidationProfile,
)
from obi_one.scientific.validations.memodel.task import (
    MEModelValidationSingleConfig,
    MEModelValidationTask,
)
from obi_one.scientific.validations.memodel.tests import (
    BPAPTest,
    _count_bpap_spikes,
)
from obi_one.scientific.validations.memodel.workflow import (
    MEModelValidationWorkflow,
    MEModelWorkflowContext,
)


def _make_mock_bpap() -> MagicMock:
    bpap = MagicMock()
    bpap.cell.get_time.return_value = np.array([0.0, 1000.0, 1500.0])
    bpap.stim_start = 1000.0
    bpap.stim_duration = 2.0
    bpap.get_recordings.return_value = (
        np.array([-70.0, -70.0, -70.0]),
        {},
        {},
    )
    bpap.get_amplitudes_and_distances.return_value = (
        [30.0],
        [10.0],
        [100.0],
        None,
        None,
    )
    bpap.validate.return_value = (True, "attenuation passed")
    bpap.plot_amp_vs_dist.return_value = None
    bpap.plot_recordings.return_value = None
    return bpap


class TestMEModelValidationWorkflow:
    def test_get_tests_default_presets(self, tmp_path):
        workflow = MEModelValidationWorkflow(output_dir=tmp_path)
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            out_dir=tmp_path,
        )
        tests = workflow.get_tests(context)
        assert len(tests) == 2  # spiking and depolarization-block presets
        assert [test.name for test in tests] == [
            "Simulatable Neuron Spiking Validation",
            "Simulatable Neuron Depolarization Block Validation",
        ]

    def test_get_tests_thalamic_profile(self, tmp_path):
        workflow = MEModelValidationWorkflow(
            output_dir=tmp_path,
            validation_profile=ThalamicMEModelValidationProfile(),
        )
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            rin=100.0,
            out_dir=tmp_path,
        )

        tests = workflow.get_tests(context)

        assert [test.name for test in tests] == [
            "Simulatable Neuron Spiking Validation",
            "Simulatable Neuron Depolarization Block Validation",
            "Simulatable Neuron Rebound Burst Validation",
            "Simulatable Neuron Back-propagating Action Potential Validation",
            "Simulatable Neuron AIS Spiking Validation",
            "Simulatable Neuron Hyperpolarization Validation",
            "Simulatable Neuron Input Resistance Validation",
            "Simulatable Neuron IV Curve Validation",
            "Simulatable Neuron FI Curve Validation",
        ]
        assert len(tests) == 9
        assert sum(test.name == "Simulatable Neuron Spiking Validation" for test in tests) == 1

        tonic_spiking = tests[0]
        assert isinstance(tonic_spiking.protocol, SequenceProtocol)
        assert tonic_spiking.protocol.measurement_phase == 1
        assert tonic_spiking.protocol.add_hypamp is True
        assert tonic_spiking.protocol.phases[0][0] == pytest.approx(500.0)
        assert tonic_spiking.protocol.phases[0][1] == pytest.approx(0.05)
        assert tonic_spiking.protocol.phases[1][0] == pytest.approx(1350.0)
        assert tonic_spiking.protocol.phases[1][1] == pytest.approx(0.13)

        depolarization_block = tests[1]
        assert isinstance(depolarization_block.protocol, StepProtocol)
        assert depolarization_block.protocol.threshold_percentage == 200.0  # ruff: ignore[float-equality-comparison]

        assert isinstance(tests[2].protocol, SequenceProtocol)
        assert tests[2].protocol.measurement_phase == 2
        assert tests[2].protocol.phases[0][0] == pytest.approx(250.0)
        assert tests[2].protocol.phases[0][1] == pytest.approx(0.10)
        assert tests[2].protocol.phases[1][0] == pytest.approx(500.0)
        assert tests[2].protocol.phases[1][1] == pytest.approx(-0.40)
        assert tests[2].protocol.phases[2][0] == pytest.approx(1000.0)
        assert tests[2].protocol.phases[2][1] == pytest.approx(0.10)
        bpap = tests[3]
        assert isinstance(bpap, BPAPTest)
        assert bpap.amplitude_factor == pytest.approx(14.6)
        assert bpap.expected_spike_count == 1
        assert bpap.sim_duration == pytest.approx(1500.0)
        assert bpap.stim_duration == pytest.approx(2.0)
        assert bpap.holding_current is None
        assert bpap.simulator_config.v_init == pytest.approx(-70.0)

    def test_thalamic_profile_forwards_explicit_bpap_holding_current(self, tmp_path):
        profile = ThalamicMEModelValidationProfile(bpap_holding_current=0.065)
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            rin=100.0,
            out_dir=tmp_path,
            simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
        )

        bpap = profile.build_tests(context)[3]

        assert isinstance(bpap, BPAPTest)
        assert bpap.holding_current == pytest.approx(0.065)
        assert bpap.stim_duration == pytest.approx(2.0)

    def test_extracts_simulator_configuration_from_hoc(self, tmp_path):
        hoc_path = tmp_path / "model.hoc"
        hoc_path.write_text(
            """proc check_simulator() {
  check_parameter(\"celsius\", 31.5, celsius)
  check_parameter(\"v_init\", -62.5, v_init)
}
""",
            encoding="utf-8",
        )

        expected = SimulatorConfig(celsius=31.5, v_init=-62.5)
        assert extract_simulator_config_from_hoc(hoc_path) == expected
        assert (
            load_simulator_config_from_hoc(
                hoc_path,
                fallback=SimulatorConfig(celsius=34.0, v_init=-80.0),
            )
            == expected
        )

    def test_hoc_loader_uses_explicit_fallback_when_undeclared(self, tmp_path):
        hoc_path = tmp_path / "model.hoc"
        hoc_path.write_text("begintemplate Cell\nendtemplate Cell\n", encoding="utf-8")
        fallback = SimulatorConfig(celsius=34.0, v_init=-80.0)

        assert load_simulator_config_from_hoc(hoc_path, fallback=fallback) == fallback
        with pytest.raises(ValueError, match="no simulator declarations"):
            load_simulator_config_from_hoc(hoc_path)

    @pytest.mark.parametrize(
        "source",
        [
            'check_parameter("celsius", 25, celsius)\n',
            (
                'check_parameter("celsius", 25, celsius)\n'
                'check_parameter("celsius", 34, celsius)\n'
                'check_parameter("v_init", -70, v_init)\n'
            ),
        ],
        ids=["partial", "conflicting"],
    )
    def test_rejects_partial_or_conflicting_hoc_declarations(self, tmp_path, source):
        hoc_path = tmp_path / "model.hoc"
        hoc_path.write_text(source, encoding="utf-8")

        with pytest.raises(ValueError, match=r"partial|conflicting"):
            extract_simulator_config_from_hoc(hoc_path)

    def test_thalamic_profile_uses_context_simulator_configuration(self, tmp_path):
        simulator_config = SimulatorConfig(celsius=31.5, v_init=-62.5)
        workflow = MEModelValidationWorkflow(
            output_dir=tmp_path,
            validation_profile=ThalamicMEModelValidationProfile(),
        )
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            rin=100.0,
            simulator_config=simulator_config,
            out_dir=tmp_path,
        )

        tests = workflow.get_tests(context)

        assert tests[0].protocol.phases[0][1] == pytest.approx(-0.025)
        assert tests[2].protocol.phases[0][1] == pytest.approx(0.025)
        assert tests[3].simulator_config == simulator_config
        assert tests[7].simulator_config == simulator_config
        assert tests[8].simulator_config == simulator_config

    def test_bpap_applies_v_init_at_simulation_boundary(self, tmp_path):
        neuron_globals = NeuronGlobals.get_instance()
        saved_params = neuron_globals.export_params()
        observed_v_init = []
        bpap = MagicMock()
        bpap.cell.get_time.return_value = np.array([0.0, 1000.0, 1500.0])
        bpap.stim_start = 1000.0
        bpap.stim_duration = 5.0
        bpap.get_recordings.return_value = (
            np.array([-70.0, -70.0, -70.0]),
            {},
            {},
        )
        bpap.run.side_effect = lambda **_: observed_v_init.append(neuron_globals.v_init)
        bpap.get_amplitudes_and_distances.return_value = ([], {}, [], {}, [])

        def construct_cell(_template_params):
            neuron_globals.v_init = -80.0
            return MagicMock()

        with (
            patch("obi_one.scientific.validations.memodel.tests.BPAP", return_value=bpap),
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                side_effect=construct_cell,
            ),
        ):
            BPAPTest(simulator_config=SimulatorConfig(celsius=34.0, v_init=65.0)).run(
                MagicMock(), 1.0, tmp_path
            )

        assert observed_v_init == [pytest.approx(65.0)]
        assert neuron_globals.export_params() == saved_params

    def test_bpap_requires_shared_simulator_configuration(self):
        with pytest.raises(TypeError, match="simulator_config"):
            BPAPTest()
        with pytest.raises(TypeError, match="unexpected keyword argument 'v_init'"):
            BPAPTest(v_init=65.0)

    def test_bpap_applies_explicit_holding_current(self, tmp_path):
        bpap = _make_mock_bpap()
        cell = MagicMock()
        cell.hypamp = 0.0
        with (
            patch("obi_one.scientific.validations.memodel.tests.BPAP", return_value=bpap),
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=cell,
            ),
        ):
            result = BPAPTest(
                holding_current=0.065,
                simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
            ).run(MagicMock(), 1.0, tmp_path)

        assert result.passed is True
        assert cell.hypamp == pytest.approx(0.065)
        bpap.run.assert_called_once_with(duration=1500.0, amplitude=10.0)

    def test_bpap_counts_late_spikes_over_full_recording(self, tmp_path):
        bpap = _make_mock_bpap()
        bpap.plot_amp_vs_dist.return_value = tmp_path / "back-propagating_action_potential.pdf"
        bpap.plot_recordings.return_value = tmp_path / "back-propagating_action_potential_recordings.pdf"
        with (
            patch("obi_one.scientific.validations.memodel.tests.BPAP", return_value=bpap),
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests._count_bpap_spikes",
                return_value=2,
            ),
        ):
            result = BPAPTest(
                expected_spike_count=1,
                simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
            ).run(MagicMock(), 1.0, tmp_path)

        assert result.passed is False
        assert "Full-trace soma spike count=2" in result.details
        assert len(result.figures) == 2
        assert {
            figure.name for figure in result.figures
        } == {
            "back-propagating_action_potential.pdf",
            "back-propagating_action_potential_recordings.pdf",
        }
        bpap.plot_recordings.assert_called_once_with(
            show_figure=False,
            save_figure=True,
            output_dir=tmp_path,
            output_fname="back-propagating_action_potential_recordings.pdf",
        )

    def test_bpap_preserves_dendritic_attenuation_failure(self, tmp_path):
        bpap = _make_mock_bpap()
        bpap.validate.return_value = (False, "attenuation failed")
        with (
            patch("obi_one.scientific.validations.memodel.tests.BPAP", return_value=bpap),
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests._count_bpap_spikes",
                return_value=1,
            ),
        ):
            result = BPAPTest(
                expected_spike_count=1,
                simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
            ).run(MagicMock(), 1.0, tmp_path)

        assert result.passed is False
        assert "attenuation failed" in result.details
        assert "Full-trace soma spike count=1" in result.details

    def test_bpap_does_not_add_figures_when_soma_has_no_ap(self, tmp_path):
        bpap = _make_mock_bpap()
        bpap.get_amplitudes_and_distances.return_value = ([], {}, [], {}, [])
        with (
            patch("obi_one.scientific.validations.memodel.tests.BPAP", return_value=bpap),
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests._count_bpap_spikes",
                return_value=0,
            ),
        ):
            result = BPAPTest(
                expected_spike_count=1,
                simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
            ).run(MagicMock(), 1.0, tmp_path)

        assert result.passed is False
        assert "No action potential detected in soma" in result.details
        assert "Full-trace soma spike count=0" in result.details
        assert result.figures == []
        bpap.plot_amp_vs_dist.assert_not_called()
        bpap.plot_recordings.assert_not_called()
        bpap.validate.assert_not_called()

    def test_bpap_spike_counter_uses_complete_trace(self):
        time = np.arange(0.0, 1500.025, 0.025)
        voltage = np.full(time.shape, -70.0)
        for center in (1001.0, 1100.0):
            relative_time = time - center
            rising = (relative_time >= -0.5) & (relative_time < 0.0)
            voltage[rising] = -70.0 + 110.0 * (relative_time[rising] + 0.5) / 0.5
            falling = (relative_time >= 0.0) & (relative_time < 0.5)
            voltage[falling] = 40.0 - 110.0 * relative_time[falling] / 0.5

        assert _count_bpap_spikes(
            time,
            voltage,
            start=0.0,
            end=1500.0,
            threshold=-20.0,
        ) == 2

    def test_accepts_custom_profile(self, tmp_path):
        custom = MagicMock()
        custom.name = "Custom Profile Test"

        class CustomProfile(MEModelValidationProfile):
            profile_name = "custom-test"

            def build_tests(self, context):
                _ = context
                return [custom]

        workflow = MEModelValidationWorkflow(
            output_dir=tmp_path,
            validation_profile=CustomProfile(),
        )
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            out_dir=tmp_path,
        )

        assert workflow.get_tests(context) == [custom]

    def test_get_tests_with_custom(self, tmp_path):
        custom = MagicMock()
        custom.name = "Custom Test"
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, custom_tests=[custom])
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            out_dir=tmp_path,
        )
        tests = workflow.get_tests(context)
        assert len(tests) == 3
        assert tests[2] == custom

    def test_run_executes_all_tests(self, tmp_path):
        mock_test = MagicMock()
        mock_test.run.return_value = TestResult(name="Mock Test", passed=True, details="ok")
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, custom_tests=[mock_test])
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params="tparams",
            rheobase=0.5,
            out_dir=tmp_path,
        )

        # Patch get_tests to return only our mock
        with patch.object(workflow, "get_tests", return_value=[mock_test]):
            test_results = workflow.run(context)

        assert len(test_results) == 1
        assert test_results[0].passed is True
        mock_test.run.assert_called_once_with("tparams", 0.5, tmp_path)

    @patch("obi_one.scientific.validations.memodel.workflow.register_outcomes")
    def test_register_delegates(self, mock_reg, tmp_path):
        workflow = MEModelValidationWorkflow(output_dir=tmp_path)
        context = MEModelWorkflowContext(
            entity_id="ent-123",
            out_dir=tmp_path,
        )
        test_results = [TestResult(name="X", passed=True, details="y")]
        client = MagicMock()

        workflow.register(test_results, context, client)

        mock_reg.assert_called_once_with(
            client=client,
            test_results=test_results,
            validated_entity_id="ent-123",
            out_dir=tmp_path,
            overwrite_existing=False,
        )


class TestMEModelValidationTask:
    def test_named_profile_is_forwarded(self, tmp_path):
        config = MEModelValidationSingleConfig(
            entity_id="test-id",
            output_dir=str(tmp_path),
            validation_profile="thalamic",
        )
        task = MEModelValidationTask(config=config)

        workflow = task.get_workflow()

        assert isinstance(workflow.validation_profile, ThalamicMEModelValidationProfile)


class TestSpikingPreset:
    def test_creates_parametric_validation(self):
        preset = spiking_preset()
        assert preset.name == "Simulatable Neuron Spiking Validation"
        assert isinstance(preset.protocol, StepProtocol)
        assert preset.protocol.threshold_percentage == 130.0  # ruff: ignore[float-equality-comparison]
        assert isinstance(preset.measurement, EfelMeasurement)
        assert preset.measurement.feature_name == "Spikecount"
        assert isinstance(preset.criterion, GreaterThan)
        assert preset.criterion.threshold == 0

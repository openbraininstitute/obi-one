"""Tests for MEModel validation workflow."""

from unittest.mock import MagicMock, patch

from bluecellulab.validation import EfelMeasurement, GreaterThan, StepProtocol
from bluecellulab.validation.base import TestResult

from obi_one.scientific.validations.memodel.presets import spiking_preset
from obi_one.scientific.validations.memodel.workflow import (
    MEModelValidationWorkflow,
    MEModelWorkflowContext,
)


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
        assert len(tests) == 1  # just spiking preset
        assert tests[0].name == "Simulatable Neuron Spiking Validation"

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
        assert len(tests) == 2
        assert tests[1] == custom

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
            skip_if_exists=True,
        )


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

"""Tests for MEModel validation workflow."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bluecellulab.validation.base import ValidationOutcome
from obi_one.scientific.validations.base import WorkflowContext
from obi_one.scientific.validations.memodel.presets import spiking_preset
from obi_one.scientific.validations.memodel.workflow import MEModelValidationWorkflow


class TestMEModelValidationWorkflow:
    def test_get_tests_default_presets(self, tmp_path):
        workflow = MEModelValidationWorkflow(output_dir=tmp_path)
        context = WorkflowContext(
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
        context = WorkflowContext(
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
        mock_test.run.return_value = ValidationOutcome(
            name="Mock Test", passed=True, details="ok"
        )
        workflow = MEModelValidationWorkflow(output_dir=tmp_path, custom_tests=[mock_test])
        context = WorkflowContext(
            entity_id="test-id",
            template_params="tparams",
            rheobase=0.5,
            out_dir=tmp_path,
        )

        # Patch get_tests to return only our mock
        with patch.object(workflow, "get_tests", return_value=[mock_test]):
            outcomes = workflow.run(context)

        assert len(outcomes) == 1
        assert outcomes[0].passed is True
        mock_test.run.assert_called_once_with("tparams", 0.5, tmp_path)

    @patch("obi_one.scientific.validations.memodel.workflow.register_outcomes")
    def test_register_delegates(self, mock_reg, tmp_path):
        workflow = MEModelValidationWorkflow(output_dir=tmp_path)
        context = WorkflowContext(
            entity_id="ent-123",
            out_dir=tmp_path,
        )
        outcomes = [ValidationOutcome(name="X", passed=True, details="y")]
        client = MagicMock()

        workflow.register(outcomes, context, client)

        mock_reg.assert_called_once_with(
            client=client,
            outcomes=outcomes,
            validated_entity_id="ent-123",
            out_dir=tmp_path,
            skip_if_exists=True,
        )


class TestSpikingPreset:
    def test_creates_parametric_validation(self):
        preset = spiking_preset()
        assert preset.name == "Simulatable Neuron Spiking Validation"
        assert preset.protocol.threshold_percentage == 130.0
        assert preset.measurement.feature_name == "Spikecount"
        assert preset.criterion.threshold == 0

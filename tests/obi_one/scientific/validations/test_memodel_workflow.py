"""Tests for MEModel validation workflow."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from bluecellulab.simulation.neuron_globals import NeuronGlobals
from bluecellulab.validation.base import TestResult
from bluecellulab.validation.criterion import GreaterThan, IsFalse
from bluecellulab.validation.measurement import EfelMeasurement
from bluecellulab.validation.protocol import SequenceProtocol, StepProtocol
from entitysdk.schemas.memodel import DownloadedMEModel

from obi_one.scientific.validations.base import (
    InvalidValidationContextError,
    ValidationRegistrationError,
    ValidationSingleConfig,
    ValidationTask,
)
from obi_one.scientific.validations.memodel.config import (
    SimulatorConfig,
    extract_simulator_config_from_hoc,
    load_simulator_config_from_hoc,
)
from obi_one.scientific.validations.memodel.presets import (
    spiking_preset,
    thalamic_depolarization_block_preset,
)
from obi_one.scientific.validations.memodel.profiles import (
    DefaultMEModelValidationProfile,
    MEModelValidationProfile,
    ThalamicMEModelValidationProfile,
    get_validation_profile,
    register_validation_profile,
)
from obi_one.scientific.validations.memodel.task import (
    MEModelValidationSingleConfig,
    MEModelValidationTask,
)
from obi_one.scientific.validations.memodel.tests import (
    AISSpikingTest,
    BPAPTest,
    FICurveTest,
    HyperpolarizationTest,
    IVCurveTest,
    RinTest,
    _count_bpap_spikes,
)
from obi_one.scientific.validations.memodel.workflow import (
    MEModelValidationWorkflow,
    MEModelWorkflowContext,
    _select_morphology_path,
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
            "Spiking Validation",
            "Depolarization Block Validation",
        ]

    def test_get_tests_thalamic_profile(self, tmp_path):
        workflow = MEModelValidationWorkflow(
            output_dir=tmp_path,
            validation_profile=ThalamicMEModelValidationProfile(),
        )
        template_params = MagicMock()
        template_params.emodel_properties.holding_current = -0.03
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=template_params,
            rheobase=1.0,
            rin=100.0,
            out_dir=tmp_path,
        )

        tests = workflow.get_tests(context)

        assert [test.name for test in tests] == [
            "Spiking Validation",
            "Depolarization Block Validation",
            "Rebound Burst Validation",
            "Back-propagating Action Potential Validation",
            "AIS Spiking Validation",
            "Hyperpolarization Validation",
            "Input Resistance Validation",
            "IV Curve Validation",
            "FI Curve Validation",
        ]
        assert len(tests) == 9
        assert sum(test.name == "Spiking Validation" for test in tests) == 1

        # Tonic firing applies the calibrated hold via add_hypamp, so the step
        # phase carries only the +0.4 nA step (phase 0 is 0 on top of the hold).
        tonic_spiking = tests[0]
        assert isinstance(tonic_spiking.protocol, SequenceProtocol)
        assert tonic_spiking.protocol.measurement_phase == 1
        assert tonic_spiking.protocol.add_hypamp is True
        assert tonic_spiking.protocol.phases[0][0] == pytest.approx(500.0)
        assert tonic_spiking.protocol.phases[0][1] == pytest.approx(0.0)
        assert tonic_spiking.protocol.phases[1][0] == pytest.approx(1350.0)
        assert tonic_spiking.protocol.phases[1][1] == pytest.approx(0.4)

        # Thalamic depol block applies the calibrated hold via add_hypamp, then
        # steps at 200% rheobase (1.0 nA -> 2.0 nA) on top of the hold.
        depolarization_block = tests[1]
        assert isinstance(depolarization_block.protocol, SequenceProtocol)
        assert depolarization_block.protocol.measurement_phase == 1
        assert depolarization_block.protocol.add_hypamp is True
        assert depolarization_block.protocol.phases[0][0] == pytest.approx(500.0)
        assert depolarization_block.protocol.phases[0][1] == pytest.approx(0.0)
        assert depolarization_block.protocol.phases[1][0] == pytest.approx(1350.0)
        assert depolarization_block.protocol.phases[1][1] == pytest.approx(2.0)

        assert isinstance(tests[2].protocol, SequenceProtocol)
        assert tests[2].protocol.measurement_phase == 2
        assert tests[2].protocol.add_hypamp is False
        assert tests[2].protocol.pre_delay == pytest.approx(0.0)
        assert tests[2].protocol.post_delay == pytest.approx(0.0)
        assert tests[2].protocol.phases[0][0] == pytest.approx(5000.0)
        assert tests[2].protocol.phases[0][1] == pytest.approx(0.04140625)
        assert tests[2].protocol.phases[1][0] == pytest.approx(500.0)
        assert tests[2].protocol.phases[1][1] == pytest.approx(-0.078125)
        assert tests[2].protocol.phases[2][0] == pytest.approx(19500.0)
        assert tests[2].protocol.phases[2][1] == pytest.approx(0.04140625)
        bpap = tests[3]
        assert isinstance(bpap, BPAPTest)
        assert bpap.amplitude_factor == pytest.approx(30.0)
        assert bpap.expected_spike_count == 1
        assert bpap.sim_duration == pytest.approx(1500.0)
        assert bpap.stim_duration == pytest.approx(2.0)
        assert bpap.holding_current is None
        assert bpap.simulator_config.v_init == pytest.approx(-70.0)

    def test_thalamic_profile_forwards_explicit_bpap_holding_current(self, tmp_path):
        profile = ThalamicMEModelValidationProfile(bpap_holding_current=0.065)
        template_params = MagicMock()
        template_params.emodel_properties.holding_current = -0.03
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=template_params,
            rheobase=1.0,
            rin=100.0,
            out_dir=tmp_path,
            simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
        )

        bpap = profile.build_tests(context)[3]

        assert isinstance(bpap, BPAPTest)
        assert bpap.holding_current == pytest.approx(0.065)
        assert bpap.stim_duration == pytest.approx(2.0)

    def _thalamic_context(self, tmp_path, calibrated_hold=-0.03):
        template_params = MagicMock()
        # Pre-held tests read the calibrated hold off emodel_properties
        # (applied via add_hypamp), so the context must carry a nonzero one.
        template_params.emodel_properties.holding_current = calibrated_hold
        return MEModelWorkflowContext(
            entity_id="test-id",
            template_params=template_params,
            rheobase=1.0,
            rin=100.0,
            out_dir=tmp_path,
            simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
        )

    def test_thalamic_tonic_step_defaults_to_paper_value(self, tmp_path):
        profile = ThalamicMEModelValidationProfile()
        context = self._thalamic_context(tmp_path)

        tonic = profile.build_tests(context)[0]

        # The hold comes from the calibrated hypamp via add_hypamp, so the step
        # phase carries only the step current (not hold + step).
        assert tonic.protocol.add_hypamp is True
        assert tonic.protocol.phases[0][1] == pytest.approx(0.0)
        assert tonic.protocol.phases[1][1] == pytest.approx(0.4)

    def test_thalamic_tonic_step_is_configurable_per_etype(self, tmp_path):
        profile = ThalamicMEModelValidationProfile(tonic_step_current=0.8)
        context = self._thalamic_context(tmp_path)

        tonic = profile.build_tests(context)[0]

        assert tonic.protocol.phases[1][1] == pytest.approx(0.8)

    def test_thalamic_pre_held_tests_require_calibrated_hold(self, tmp_path):
        # A zero/missing calibrated hold must fail loudly, not validate at the
        # cell's bare resting potential.
        profile = ThalamicMEModelValidationProfile()
        context = self._thalamic_context(tmp_path, calibrated_hold=0.0)

        with pytest.raises(InvalidValidationContextError, match="calibrated holding current"):
            profile.build_tests(context)

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
        template_params = MagicMock()
        template_params.emodel_properties.holding_current = -0.025
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=template_params,
            rheobase=1.0,
            rin=100.0,
            simulator_config=simulator_config,
            out_dir=tmp_path,
        )

        tests = workflow.get_tests(context)

        # Tonic firing applies the calibrated hold via add_hypamp; the step
        # phase carries only the step current.
        assert tests[0].protocol.add_hypamp is True
        assert tests[0].protocol.phases[0][1] == pytest.approx(0.0)
        # Rebound burst holds at the fixed calibrated current, not the pre-hold.
        assert tests[2].protocol.phases[0][1] == pytest.approx(0.04140625)
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
            BPAPTest()  # ty: ignore[missing-argument]  # Intentional runtime contract check.
        with pytest.raises(TypeError, match="unexpected keyword argument 'v_init'"):
            BPAPTest(  # ty: ignore[missing-argument]  # Intentional contract check.
                v_init=65.0,  # ty: ignore[unknown-argument]  # Intentional contract check.
            )

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
        bpap.plot_recordings.return_value = (
            tmp_path / "back-propagating_action_potential_recordings.pdf"
        )
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
        assert {figure.name for figure in result.figures} == {
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

        assert (
            _count_bpap_spikes(
                time,
                voltage,
                start=0.0,
                end=1500.0,
                threshold=-20.0,
            )
            == 2
        )

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


class TestSelectMorphologyPath:
    """Guards the entitysdk DownloadedMEModel contract this workflow depends on.

    ``_select_morphology_path`` reads ``morphology_paths`` (a list) off the
    downloaded model and uses the first. If entitysdk renames or reshapes that
    field, these fail here rather than only at runtime inside a notebook.
    """

    def _downloaded(self, tmp_path, morphology_names=("morph.asc",)):
        hoc_path = tmp_path / "model.hoc"
        mechanisms_dir = tmp_path / "mechanisms"
        mechanisms_dir.mkdir()
        hoc_path.write_text("")
        return DownloadedMEModel(
            hoc_path=hoc_path,
            mechanisms_dir=mechanisms_dir,
            mechanism_files=[],
            morphology_paths=[tmp_path / name for name in morphology_names],
        )

    def test_schema_exposes_morphology_paths_list(self):
        assert "morphology_paths" in DownloadedMEModel.model_fields
        assert "morphology_path" not in DownloadedMEModel.model_fields

    def test_prefers_asc_over_other_formats(self, tmp_path):
        # Order deliberately puts h5/swc before asc to prove it selects by
        # format, not position.
        downloaded = self._downloaded(
            tmp_path, morphology_names=("morph.h5", "morph.swc", "morph.asc")
        )

        result = _select_morphology_path(downloaded, "ent-123")

        assert result.suffix == ".asc"

    def test_falls_back_to_swc_when_no_asc(self, tmp_path):
        downloaded = self._downloaded(tmp_path, morphology_names=("morph.h5", "morph.swc"))

        result = _select_morphology_path(downloaded, "ent-123")

        assert result.suffix == ".swc"

    def test_raises_when_no_loadable_morphology(self, tmp_path):
        downloaded = self._downloaded(tmp_path, morphology_names=("morph.h5",))

        with pytest.raises(InvalidValidationContextError, match="ent-123"):
            _select_morphology_path(downloaded, "ent-123")

    def test_raises_when_no_morphology(self, tmp_path):
        downloaded = self._downloaded(tmp_path, morphology_names=())

        with pytest.raises(InvalidValidationContextError, match="ent-123"):
            _select_morphology_path(downloaded, "ent-123")


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
        assert preset.name == "Spiking Validation"
        assert isinstance(preset.protocol, StepProtocol)
        assert preset.protocol.threshold_percentage == 130.0  # ruff: ignore[float-equality-comparison]
        assert isinstance(preset.measurement, EfelMeasurement)
        assert preset.measurement.feature_name == "Spikecount"
        assert isinstance(preset.criterion, GreaterThan)
        assert preset.criterion.threshold == 0


class TestThalamicDepolarizationBlockPreset:
    def test_step_is_rheobase_scaled_on_top_of_calibrated_hold(self):
        # The calibrated hold is applied via add_hypamp, so the step phase
        # carries only 200% of rheobase (2.0 nA -> 4.0 nA); phase 0 is 0.
        preset = thalamic_depolarization_block_preset(rheobase=2.0)
        assert preset.name == "Depolarization Block Validation"
        assert isinstance(preset.protocol, SequenceProtocol)
        assert preset.protocol.amplitude_mode == "amplitude"
        assert preset.protocol.measurement_phase == 1
        assert preset.protocol.add_hypamp is True
        assert preset.protocol.phases[0][0] == pytest.approx(500.0)
        assert preset.protocol.phases[0][1] == pytest.approx(0.0)
        assert preset.protocol.phases[1][0] == pytest.approx(1350.0)
        assert preset.protocol.phases[1][1] == pytest.approx(4.0)
        assert isinstance(preset.measurement, EfelMeasurement)
        assert preset.measurement.feature_name == "depol_block_bool"
        assert isinstance(preset.criterion, IsFalse)

    def test_step_scales_with_rheobase(self):
        preset = thalamic_depolarization_block_preset(rheobase=1.0)
        assert preset.protocol.phases[0][1] == pytest.approx(0.0)
        assert preset.protocol.phases[1][1] == pytest.approx(2.0)


class TestIVCurveTest:
    def _sim_config(self):
        return SimulatorConfig(celsius=34.0, v_init=-70.0)

    def test_passes_the_rheobase_scaled_bounds(self, tmp_path):
        # The sweep is pinned to the cell's rheobase here, not inherited from the
        # bluecellulab default, so the exact bounds are part of the contract.
        with (
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.compute_plot_iv_curve",
                return_value=(np.array([-0.2, 0.0, 0.18]), np.array([-80.0, -70.0, -60.0])),
            ) as mock_iv,
        ):
            result = IVCurveTest(simulator_config=self._sim_config()).run(
                MagicMock(), 0.2, tmp_path
            )

        assert result.passed is True
        kwargs = mock_iv.call_args.kwargs
        assert kwargs["min_amp"] == pytest.approx(-0.2)
        assert kwargs["max_amp"] == pytest.approx(0.18)

    def test_fails_on_negative_slope(self, tmp_path):
        with (
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.compute_plot_iv_curve",
                return_value=(np.array([-0.2, 0.0, 0.18]), np.array([-60.0, -70.0, -80.0])),
            ),
        ):
            result = IVCurveTest(simulator_config=self._sim_config()).run(
                MagicMock(), 0.2, tmp_path
            )

        assert result.passed is False

    def test_fails_without_raising_when_range_invalid(self, tmp_path):
        # A rheobase <= 0 makes compute_plot_iv_curve raise; the test must fail
        # rather than abort the whole validation run.
        with (
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.compute_plot_iv_curve",
                side_effect=ValueError("finite positive rheobase"),
            ),
        ):
            result = IVCurveTest(simulator_config=self._sim_config()).run(
                MagicMock(), 0.0, tmp_path
            )

        assert result.passed is False
        assert "finite positive rheobase" in result.details
        assert result.figures == []


class TestMEModelValidationProfiles:
    def _context(self, tmp_path, *, rin=100.0, rheobase=1.0, calibrated_hold=-0.03):
        template_params = MagicMock()
        template_params.emodel_properties.holding_current = calibrated_hold
        return MEModelWorkflowContext(
            entity_id="test-id",
            template_params=template_params,
            rheobase=rheobase,
            rin=rin,
            out_dir=tmp_path,
            simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
        )

    def test_default_profile_builds_spiking_and_depol_block(self, tmp_path):
        tests = DefaultMEModelValidationProfile().build_tests(self._context(tmp_path))
        names = [t.name for t in tests]
        assert names == ["Spiking Validation", "Depolarization Block Validation"]

    def test_thalamic_requires_rin_and_holding(self):
        profile = ThalamicMEModelValidationProfile()
        assert profile.requires_rin is True
        assert profile.requires_holding_current is True
        assert profile.recompute_rheobase is True

    def test_thalamic_builds_full_nine_test_policy(self, tmp_path):
        tests = ThalamicMEModelValidationProfile().build_tests(self._context(tmp_path))
        assert len(tests) == 9

    def test_thalamic_requires_rin(self, tmp_path):
        profile = ThalamicMEModelValidationProfile()
        context = self._context(tmp_path, rin=None)
        with pytest.raises(InvalidValidationContextError, match="Rin"):
            profile.build_tests(context)

    def test_thalamic_requires_rheobase(self, tmp_path):
        profile = ThalamicMEModelValidationProfile()
        context = self._context(tmp_path, rheobase=None)
        with pytest.raises(InvalidValidationContextError, match="rheobase"):
            profile.build_tests(context)

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"tonic_step_current": 0.0}, "positive finite"),
            ({"tonic_step_current": float("nan")}, "positive finite"),
            ({"bpap_amplitude_factor": -1.0}, "positive finite"),
            ({"rebound_hyperpolarization_duration_ms": 0.0}, "positive finite"),
            ({"bpap_holding_current": float("inf")}, "finite number"),
            ({"rebound_holding_current": float("nan")}, "finite number"),
            ({"bpap_trace_diagnostics": "yes"}, "must be a boolean"),
        ],
    )
    def test_thalamic_constructor_rejects_invalid_values(self, kwargs, match):
        with pytest.raises((TypeError, ValueError), match=match):
            ThalamicMEModelValidationProfile(**kwargs)

    def test_thalamic_accepts_optional_none(self):
        # None is valid for the optional currents; it means "use the default".
        profile = ThalamicMEModelValidationProfile(
            bpap_holding_current=None,
            rebound_holding_current=None,
            rebound_hyperpolarization_amplitude=None,
        )
        assert profile.bpap_holding_current is None
        assert profile.rebound_holding_current is None


class TestValidationTaskExecute:
    """Covers the entity-agnostic orchestration in ValidationTask.execute."""

    def _make_task(self, registered):
        workflow = MagicMock()
        workflow.setup.return_value = SimpleNamespace(entity_id="e1")
        workflow.run.return_value = [MagicMock()]
        workflow.register.return_value = registered

        class _Task(ValidationTask):
            config: ValidationSingleConfig

            def get_workflow(self):
                return workflow

        task = _Task(config=ValidationSingleConfig(entity_id="e1"))
        # The execution-activity bookkeeping comes from the Task base and needs
        # no DB for this orchestration test.
        task._get_execution_activity = MagicMock(return_value=MagicMock())
        task._update_execution_activity = MagicMock()
        return task, workflow

    def _result(self, name, entity_id, *, skipped=False):
        return SimpleNamespace(
            entity_id=entity_id,
            skipped=skipped,
            test_result=SimpleNamespace(name=name),
        )

    def test_returns_registered_ids(self):
        registered = [self._result("A", "id-A"), self._result("B", "id-B")]
        task, workflow = self._make_task(registered)

        ids = task.execute(db_client=MagicMock())

        assert ids == ["id-A", "id-B"]
        workflow.setup.assert_called_once()
        workflow.run.assert_called_once()

    def test_raises_when_a_result_fails_to_register(self):
        registered = [self._result("A", "id-A"), self._result("B", None)]
        task, _ = self._make_task(registered)

        with pytest.raises(ValidationRegistrationError, match="failed to"):
            task.execute(db_client=MagicMock())

    def test_warns_and_returns_ids_when_skipped(self, caplog):
        registered = [self._result("A", "id-A", skipped=True)]
        task, _ = self._make_task(registered)

        with caplog.at_level("WARNING"):
            ids = task.execute(db_client=MagicMock())

        assert ids == ["id-A"]
        assert any("skipped" in r.message.lower() for r in caplog.records)


class TestRinTest:
    def test_passes_below_max(self, tmp_path):
        result = RinTest(rin=100.0).run(MagicMock(), 1.0, tmp_path)
        assert result.passed is True
        assert "100.00 MOhm" in result.details
        assert result.figures == []

    def test_fails_above_max(self, tmp_path):
        result = RinTest(rin=5000.0).run(MagicMock(), 1.0, tmp_path)
        assert result.passed is False
        assert "not biologically realistic" in result.details


class TestHyperpolarizationTest:
    def _patches(self, features):
        recording = SimpleNamespace(time=np.array([0.0, 1.0]), voltage=np.array([-70.0, -75.0]))
        return (
            patch(
                "obi_one.scientific.validations.memodel.tests.run_stimulus",
                return_value=recording,
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.plot_trace",
                return_value="hyperpol.pdf",
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.efel.get_feature_values",
                return_value=features,
            ),
        )

    def test_passes_when_hyperpolarized_below_rmp(self, tmp_path):
        features = [
            {
                "voltage_base": np.array([-65.0]),
                "steady_state_voltage_stimend": np.array([-80.0]),
            }
        ]
        p1, p2, p3 = self._patches(features)
        with p1, p2, p3:
            result = HyperpolarizationTest().run(MagicMock(), 1.0, tmp_path)
        assert result.passed is True

    def test_fails_when_not_below_rmp(self, tmp_path):
        features = [
            {
                "voltage_base": np.array([-80.0]),
                "steady_state_voltage_stimend": np.array([-65.0]),
            }
        ]
        p1, p2, p3 = self._patches(features)
        with p1, p2, p3:
            result = HyperpolarizationTest().run(MagicMock(), 1.0, tmp_path)
        assert result.passed is False

    def test_fails_gracefully_when_features_missing(self, tmp_path):
        features = [{"voltage_base": None, "steady_state_voltage_stimend": None}]
        p1, p2, p3 = self._patches(features)
        with p1, p2, p3:
            result = HyperpolarizationTest().run(MagicMock(), 1.0, tmp_path)
        assert result.passed is False
        assert "Could not determine" in result.details


class TestAISSpikingTest:
    def test_skips_when_no_axon(self, tmp_path):
        cell = MagicMock()
        cell.axonal = []
        cell.sections = {}
        with patch(
            "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
            return_value=cell,
        ):
            result = AISSpikingTest().run(MagicMock(), 1.0, tmp_path)
        assert result.passed is True
        assert "does not have an axon" in result.details

    def _run_with_spike_times(self, tmp_path, axon_peak, soma_peak):
        cell = MagicMock()
        cell.axonal = [MagicMock()]
        cell.sections = {"axon[0]": MagicMock()}
        rec = SimpleNamespace(time=np.array([0.0, 1.0]), voltage=np.array([-70.0, 20.0]))
        features = [{"peak_time": axon_peak}, {"peak_time": soma_peak}]
        with (
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=cell,
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.run_multirecordings_stimulus",
                return_value=(rec, rec),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.plot_traces",
                return_value="ais.pdf",
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.efel.get_feature_values",
                return_value=features,
            ),
        ):
            return AISSpikingTest().run(MagicMock(), 1.0, tmp_path)

    def test_passes_when_axon_spikes_before_soma(self, tmp_path):
        result = self._run_with_spike_times(tmp_path, np.array([10.0]), np.array([12.0]))
        assert result.passed is True
        assert "Axon spikes before soma" in result.details

    def test_fails_when_axon_not_before_soma(self, tmp_path):
        result = self._run_with_spike_times(tmp_path, np.array([13.0]), np.array([12.0]))
        assert result.passed is False

    def test_fails_when_spike_times_missing(self, tmp_path):
        result = self._run_with_spike_times(tmp_path, None, np.array([12.0]))
        assert result.passed is False
        assert "Could not determine spike times" in result.details


class TestFICurveTest:
    def _sim_config(self):
        return SimulatorConfig(celsius=34.0, v_init=-70.0)

    def test_passes_on_positive_slope(self, tmp_path):
        with (
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.compute_plot_fi_curve",
                return_value=(np.array([0.1, 0.2, 0.3]), np.array([0, 2, 5])),
            ),
        ):
            result = FICurveTest(simulator_config=self._sim_config()).run(
                MagicMock(), 0.1, tmp_path
            )
        assert result.passed is True

    def test_fails_on_too_few_points(self, tmp_path):
        with (
            patch(
                "obi_one.scientific.validations.memodel.tests.Cell.from_template_parameters",
                return_value=MagicMock(),
            ),
            patch(
                "obi_one.scientific.validations.memodel.tests.compute_plot_fi_curve",
                return_value=(np.array([0.1]), np.array([0])),
            ),
        ):
            result = FICurveTest(simulator_config=self._sim_config()).run(
                MagicMock(), 0.1, tmp_path
            )
        assert result.passed is False
        assert "Not enough data points" in result.details


class TestValidationProfileRegistry:
    def test_get_default_when_none(self):
        profile = get_validation_profile(None)
        assert isinstance(profile, DefaultMEModelValidationProfile)

    def test_get_returns_instance_as_is(self):
        instance = ThalamicMEModelValidationProfile()
        assert get_validation_profile(instance) is instance

    def test_get_by_name(self):
        assert isinstance(get_validation_profile("thalamic"), ThalamicMEModelValidationProfile)

    def test_get_unknown_name_raises(self):
        with pytest.raises(ValueError, match="Unknown MEModel validation profile"):
            get_validation_profile("does-not-exist")

    def test_get_non_string_raises(self):
        with pytest.raises(TypeError, match="profile name or"):
            get_validation_profile(123)  # ty: ignore[invalid-argument-type]

    def test_register_and_resolve(self):
        class _Custom(DefaultMEModelValidationProfile):
            profile_name = "unit-test-custom"

        register_validation_profile("unit-test-custom", _Custom)
        assert isinstance(get_validation_profile("unit-test-custom"), _Custom)

    def test_register_empty_name_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            register_validation_profile("  ", DefaultMEModelValidationProfile)

    def test_register_wrong_type_raises(self):
        with pytest.raises(TypeError, match="must inherit from"):
            register_validation_profile("x", str)  # ty: ignore[invalid-argument-type]

    def test_register_duplicate_without_overwrite_raises(self):
        with pytest.raises(ValueError, match="already registered"):
            register_validation_profile("thalamic", ThalamicMEModelValidationProfile)

    def test_default_profile_requirement_flags_are_false(self):
        profile = DefaultMEModelValidationProfile()
        assert profile.requires_rin is False
        assert profile.requires_holding_current is False
        assert profile.recompute_rheobase is False

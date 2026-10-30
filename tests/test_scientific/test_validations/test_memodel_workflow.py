"""Tests for MEModel validation workflow."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from bluecellulab.simulation.neuron_globals import NeuronGlobals
from bluecellulab.validation.base import TestResult
from bluecellulab.validation.criterion import GreaterThan, IsFalse
from bluecellulab.validation.measurement import EfelMeasurement
from bluecellulab.validation.protocol import SequenceProtocol, StepProtocol
from entitysdk.schemas.memodel import DownloadedMEModel

from obi_one.scientific.validations.base import InvalidValidationContextError
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
    _derive_profile_holding_current,
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
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            rin=100.0,
            holding_current=-0.03,
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

        # Tonic firing pre-holds at the derived holding current (-0.03 nA),
        # then steps +0.4 nA on top of it (-> 0.37 nA).
        tonic_spiking = tests[0]
        assert isinstance(tonic_spiking.protocol, SequenceProtocol)
        assert tonic_spiking.protocol.measurement_phase == 1
        assert tonic_spiking.protocol.add_hypamp is False
        assert tonic_spiking.protocol.phases[0][0] == pytest.approx(500.0)
        assert tonic_spiking.protocol.phases[0][1] == pytest.approx(-0.03)
        assert tonic_spiking.protocol.phases[1][0] == pytest.approx(1350.0)
        assert tonic_spiking.protocol.phases[1][1] == pytest.approx(0.37)

        # Thalamic depol block pre-holds at the derived holding current
        # (-0.03 nA), then steps at 200% rheobase (1.0 nA -> 2.0 nA) on top of
        # the hold (-0.03 + 2.0 = 1.97 nA).
        depolarization_block = tests[1]
        assert isinstance(depolarization_block.protocol, SequenceProtocol)
        assert depolarization_block.protocol.measurement_phase == 1
        assert depolarization_block.protocol.add_hypamp is False
        assert depolarization_block.protocol.phases[0][0] == pytest.approx(500.0)
        assert depolarization_block.protocol.phases[0][1] == pytest.approx(-0.03)
        assert depolarization_block.protocol.phases[1][0] == pytest.approx(1350.0)
        assert depolarization_block.protocol.phases[1][1] == pytest.approx(1.97)

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
        context = MEModelWorkflowContext(
            entity_id="test-id",
            template_params=MagicMock(),
            rheobase=1.0,
            rin=100.0,
            holding_current=-0.03,
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
            holding_current=-0.025,
            simulator_config=simulator_config,
            out_dir=tmp_path,
        )

        tests = workflow.get_tests(context)

        # Tonic firing holds at the derived holding current from the context.
        assert tests[0].protocol.phases[0][1] == pytest.approx(-0.025)
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

    def test_returns_first_morphology_path(self, tmp_path):
        downloaded = self._downloaded(tmp_path, morphology_names=("morph.asc", "morph.swc"))

        result = _select_morphology_path(downloaded, "ent-123")

        assert result == downloaded.morphology_paths[0]

    def test_raises_when_no_morphology(self, tmp_path):
        downloaded = self._downloaded(tmp_path, morphology_names=())

        with pytest.raises(InvalidValidationContextError, match="ent-123"):
            _select_morphology_path(downloaded, "ent-123")


class TestDeriveProfileHoldingCurrent:
    """Deriving the pre-hold current via BlueCelluLab's search.

    The profile declares the target holding voltage; the current that reaches it
    is found by bluecellulab.tools.search_hyp_current. Profiles that step from
    rest (holding_voltage is None) skip the search and return None.
    """

    def _template_params(self):
        tp = MagicMock()
        tp.template_filepath = "model.hoc"
        tp.morph_filepath = "morph.asc"
        tp.template_format = "v6"
        tp.emodel_properties = MagicMock()
        return tp

    def test_returns_none_for_profile_without_hold(self):
        result = _derive_profile_holding_current(
            DefaultMEModelValidationProfile(), self._template_params()
        )
        assert result is None

    @patch("bluecellulab.tools.calculate_SS_voltage", return_value=-64.9)
    @patch("bluecellulab.tools.search_hyp_current", return_value=0.065)
    def test_delegates_to_bluecellulab_search_for_thalamic(self, mock_search, mock_ss):
        result = _derive_profile_holding_current(
            ThalamicMEModelValidationProfile(), self._template_params()
        )
        assert result == pytest.approx(0.065)
        # The search targets the profile's -60 mV holding voltage.
        assert mock_search.call_args.kwargs["target_voltage"] == pytest.approx(-60.0)
        # The achieved hold is read back (and logged) via calculate_SS_voltage.
        assert mock_ss.call_args.kwargs["step_level"] == pytest.approx(0.065)


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
    def test_prehold_then_rheobase_step(self):
        # Hold at the derived holding current (-0.05 nA), then step 200% of
        # rheobase (2.0 nA -> 4.0 nA) on top of the hold (-0.05 + 4.0 = 3.95 nA).
        preset = thalamic_depolarization_block_preset(
            rheobase=2.0,
            holding_current=-0.05,
        )
        assert preset.name == "Depolarization Block Validation"
        assert isinstance(preset.protocol, SequenceProtocol)
        assert preset.protocol.amplitude_mode == "amplitude"
        assert preset.protocol.measurement_phase == 1
        assert preset.protocol.add_hypamp is False
        assert preset.protocol.phases[0][0] == pytest.approx(500.0)
        assert preset.protocol.phases[0][1] == pytest.approx(-0.05)
        assert preset.protocol.phases[1][0] == pytest.approx(1350.0)
        assert preset.protocol.phases[1][1] == pytest.approx(3.95)
        assert isinstance(preset.measurement, EfelMeasurement)
        assert preset.measurement.feature_name == "depol_block_bool"
        assert isinstance(preset.criterion, IsFalse)

    def test_step_sits_on_top_of_zero_hold(self):
        preset = thalamic_depolarization_block_preset(
            rheobase=1.0,
            holding_current=0.0,
        )
        assert preset.protocol.phases[0][1] == pytest.approx(0.0)
        assert preset.protocol.phases[1][1] == pytest.approx(2.0)

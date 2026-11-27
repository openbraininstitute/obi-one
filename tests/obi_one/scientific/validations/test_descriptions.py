"""Tests for the generated ValidationResult descriptions."""

from unittest.mock import MagicMock

import pytest
from bluecellulab.validation.base import TestResult, ValidationTest
from bluecellulab.validation.criterion import GreaterThan
from bluecellulab.validation.measurement import EfelMeasurement
from bluecellulab.validation.parametric_validation import ParametricValidation
from bluecellulab.validation.protocol import SequenceProtocol, StepProtocol

from obi_one.scientific.validations.memodel.config import SimulatorConfig
from obi_one.scientific.validations.memodel.descriptions import (
    UndescribedValidationTestError,
    describe_protocol,
    describe_test,
)
from obi_one.scientific.validations.memodel.presets import (
    depolarization_block_preset,
    spiking_preset,
    tonic_firing_preset,
)
from obi_one.scientific.validations.memodel.profiles import (
    DefaultMEModelValidationProfile,
    ThalamicMEModelValidationProfile,
)
from obi_one.scientific.validations.memodel.tests import (
    BPAPTest,
    FICurveTest,
    IVCurveTest,
    RinTest,
    ThumbnailTest,
)
from obi_one.scientific.validations.memodel.workflow import MEModelWorkflowContext

HOLD = 0.04
SIMULATOR_CONFIG = SimulatorConfig(celsius=34.0, v_init=-70.0)


def _thalamic_context(tmp_path):
    template_params = MagicMock()
    template_params.emodel_properties.holding_current = -0.03
    return MEModelWorkflowContext(
        entity_id="test-id",
        template_params=template_params,
        rheobase=0.1,
        rin=200.0,
        out_dir=tmp_path,
        simulator_config=SIMULATOR_CONFIG,
    )


class TestProtocolDescriptions:
    def test_step_protocol_states_the_holding_current(self):
        assert describe_protocol(StepProtocol(threshold_percentage=130), HOLD) == (
            "Injects a step of 130% of rheobase into the soma, on top of a holding current "
            "of 0.04 nA, for 1350 ms, after 250 ms and followed by 250 ms."
        )

    def test_step_protocol_with_zero_holding_current(self):
        text = describe_protocol(StepProtocol(threshold_percentage=130), 0.0)
        assert "into the soma, with no holding current, for 1350 ms" in text

    def test_step_protocol_with_absolute_amplitude_and_no_holding(self):
        text = describe_protocol(StepProtocol(amplitude=0.25, add_hypamp=False), HOLD)
        assert text.startswith("Injects a step of 0.25 nA into the soma for 1350 ms")

    def test_sequence_protocol_without_holding_marks_the_measured_phase(self):
        protocol = SequenceProtocol(
            phases=[(5000.0, 0.04), (500.0, -0.08), (1000.0, 0.04)],
            pre_delay=0.0,
            post_delay=0.0,
            amplitude_mode="amplitude",
            add_hypamp=False,
            measurement_phase=2,
        )
        assert describe_protocol(protocol, HOLD) == (
            "Injects into the soma (total current, including any holding): 5000 ms at "
            "0.04 nA, then 500 ms at -0.08 nA, then 1000 ms at 0.04 nA (measured)."
        )

    def test_sequence_protocol_on_top_of_the_holding_current(self):
        assert describe_protocol(tonic_firing_preset(step_current=0.8).protocol, HOLD) == (
            "Injects into the soma, on top of a holding current of 0.04 nA: 500 ms with no "
            "added current, then 1350 ms at 0.8 nA (measured), followed by 250 ms."
        )

    def test_measured_phase_can_be_left_unmarked(self):
        protocol = tonic_firing_preset(step_current=0.8).protocol
        assert "(measured)" not in describe_protocol(protocol, HOLD, mark_measured=False)

    def test_unknown_protocol_is_not_described(self):
        assert not describe_protocol(MagicMock(), HOLD)


class TestPresetDescriptions:
    def test_spiking_names_feature_and_threshold(self):
        assert describe_test(spiking_preset(), HOLD).endswith(
            "Passes if the eFEL feature Spikecount (Threshold=-40) is greater than 0."
        )

    def test_depolarization_block(self):
        assert describe_test(depolarization_block_preset(), HOLD).endswith(
            "Passes if the eFEL feature depol_block_bool (depol_block_min_duration=150) is false."
        )


class TestCustomTestDescriptions:
    def test_default_thumbnail_matches_the_legacy_step(self):
        assert describe_test(ThumbnailTest(), HOLD).startswith(
            describe_protocol(StepProtocol(threshold_percentage=130), HOLD)
        )

    def test_thumbnail_does_not_mark_a_measured_phase(self):
        protocol = tonic_firing_preset(step_current=0.8).protocol
        text = describe_test(ThumbnailTest(protocol=protocol), HOLD)
        assert text.startswith(describe_protocol(protocol, HOLD, mark_measured=False))
        assert "(measured)" not in text

    def test_bpap_with_its_own_holding_current_and_spike_guard(self):
        test = BPAPTest(
            amplitude=0.5,
            stim_duration=2.0,
            holding_current=0.065,
            expected_spike_count=1,
            simulator_config=SIMULATOR_CONFIG,
        )
        assert describe_test(test, HOLD) == (
            "Injects a 2 ms pulse of 0.5 nA into the soma, on top of a holding current of "
            "0.065 nA, in a 1500 ms simulation, and records the voltage in every section. "
            "Passes if the action potential is smaller at the furthest basal and apical "
            "dendrites than at the soma, and the soma fires exactly 1 spike over the whole "
            "simulation (threshold -20 mV)."
        )

    def test_bpap_without_its_own_holding_uses_the_cells(self):
        text = describe_test(BPAPTest(simulator_config=SIMULATOR_CONFIG), HOLD)
        assert "10 times the rheobase" in text
        assert "on top of a holding current of 0.04 nA" in text
        assert "fires exactly" not in text

    def test_rin_does_not_mention_a_holding_current(self):
        assert "holding" not in describe_test(RinTest(rin=100.0), HOLD)

    def test_iv_curve_uses_the_pinned_sweep(self):
        text = describe_test(IVCurveTest(simulator_config=SIMULATOR_CONFIG), HOLD)
        assert "5 steps from -1 to 0.9 times the rheobase" in text
        assert "on top of a holding current of 0.04 nA" in text

    def test_fi_curve(self):
        text = describe_test(FICurveTest(simulator_config=SIMULATOR_CONFIG), HOLD)
        assert "5 steps from 1 to 3 times the rheobase" in text
        assert "on top of a holding current of 0.04 nA" in text

    def test_test_without_description_raises(self):
        class Undescribed(ValidationTest):
            @property
            def name(self):
                return "Undescribed"

            def run(self, template_params, rheobase, out_dir):
                _ = (template_params, rheobase, out_dir)
                return TestResult(name=self.name, passed=True, details="")

        with pytest.raises(UndescribedValidationTestError, match="Undescribed"):
            describe_test(Undescribed(), HOLD)

    def test_parametric_validation_with_unknown_criterion_raises(self):
        test = ParametricValidation(
            validation_name="Custom",
            protocol=StepProtocol(threshold_percentage=150),
            measurement=EfelMeasurement(feature_name="Spikecount"),
            criterion=MagicMock(),
        )

        with pytest.raises(UndescribedValidationTestError):
            describe_test(test, HOLD)

    def test_description_property_overrides_the_generated_text(self):
        class Described(ParametricValidation):
            @property
            def description(self):
                return "Hand-written."

        test = Described(
            validation_name="Custom",
            protocol=StepProtocol(threshold_percentage=150),
            measurement=EfelMeasurement(feature_name="Spikecount"),
            criterion=GreaterThan(threshold=0),
        )

        assert describe_test(test, HOLD) == "Hand-written."


class TestProfileDescriptions:
    @pytest.mark.parametrize(
        "profile", [DefaultMEModelValidationProfile(), ThalamicMEModelValidationProfile()]
    )
    def test_every_profile_test_is_described(self, profile, tmp_path):
        for test in profile.build_tests(_thalamic_context(tmp_path)):
            assert describe_test(test, HOLD), test.name

    def test_thalamic_thumbnail_describes_the_rebound_protocol(self, tmp_path):
        tests = ThalamicMEModelValidationProfile().build_tests(_thalamic_context(tmp_path))
        by_name = {test.name: test for test in tests}
        rebound = by_name["Rebound Burst Validation"]
        assert describe_test(by_name["thumbnail"], HOLD).startswith(
            describe_protocol(rebound.protocol, HOLD, mark_measured=False)
        )

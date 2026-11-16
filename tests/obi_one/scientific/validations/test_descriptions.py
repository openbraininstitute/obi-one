"""Tests for the generated ValidationResult descriptions."""

from unittest.mock import MagicMock

import pytest
from bluecellulab.validation.base import TestResult, ValidationTest
from bluecellulab.validation.protocol import SequenceProtocol, StepProtocol

from obi_one.scientific.validations.memodel.config import SimulatorConfig
from obi_one.scientific.validations.memodel.descriptions import describe_protocol, describe_test
from obi_one.scientific.validations.memodel.presets import (
    depolarization_block_preset,
    spiking_preset,
)
from obi_one.scientific.validations.memodel.profiles import (
    DefaultMEModelValidationProfile,
    ThalamicMEModelValidationProfile,
)
from obi_one.scientific.validations.memodel.tests import (
    BPAPTest,
    FICurveTest,
    IVCurveTest,
    ThumbnailTest,
)
from obi_one.scientific.validations.memodel.workflow import MEModelWorkflowContext


def _thalamic_context(tmp_path):
    template_params = MagicMock()
    template_params.emodel_properties.holding_current = -0.03
    return MEModelWorkflowContext(
        entity_id="test-id",
        template_params=template_params,
        rheobase=0.1,
        rin=200.0,
        out_dir=tmp_path,
        simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
    )


class TestProtocolDescriptions:
    def test_step_protocol(self):
        assert describe_protocol(StepProtocol(threshold_percentage=130)) == (
            "Injects a step of 130% of rheobase into the soma, on top of the calibrated "
            "holding current, for 1350 ms, after 250 ms and followed by 250 ms."
        )

    def test_step_protocol_with_absolute_amplitude_and_no_holding(self):
        text = describe_protocol(StepProtocol(amplitude=0.25, add_hypamp=False))
        assert text.startswith("Injects a step of 0.25 nA into the soma for 1350 ms")

    def test_sequence_protocol_marks_the_measured_phase(self):
        protocol = SequenceProtocol(
            phases=[(5000.0, 0.04), (500.0, -0.08), (1000.0, 0.04)],
            pre_delay=0.0,
            post_delay=0.0,
            amplitude_mode="amplitude",
            add_hypamp=False,
            measurement_phase=2,
        )
        assert describe_protocol(protocol) == (
            "Injects into the soma: 5000 ms at 0.04 nA, then 500 ms at -0.08 nA, then "
            "1000 ms at 0.04 nA (measured). Amplitudes are the total injected current, "
            "including any holding."
        )

    def test_unknown_protocol_is_not_described(self):
        assert not describe_protocol(MagicMock())


class TestPresetDescriptions:
    def test_spiking_names_feature_and_threshold(self):
        assert describe_test(spiking_preset()).endswith(
            "Passes if the eFEL feature Spikecount (Threshold=-40) is greater than 0."
        )

    def test_depolarization_block(self):
        assert describe_test(depolarization_block_preset()).endswith(
            "Passes if the eFEL feature depol_block_bool (depol_block_min_duration=150) is false."
        )


class TestCustomTestDescriptions:
    def test_default_thumbnail_matches_the_legacy_step(self):
        assert describe_test(ThumbnailTest()).startswith(
            describe_protocol(StepProtocol(threshold_percentage=130))
        )

    def test_thumbnail_describes_the_given_protocol(self):
        protocol = SequenceProtocol(phases=[(500.0, 0.1)], amplitude_mode="amplitude")
        assert describe_test(ThumbnailTest(protocol=protocol)).startswith(
            describe_protocol(protocol)
        )

    def test_bpap_with_absolute_amplitude_and_spike_guard(self):
        test = BPAPTest(
            amplitude=0.5,
            stim_duration=2.0,
            holding_current=0.065,
            expected_spike_count=1,
            simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0),
        )
        assert describe_test(test) == (
            "Injects a 2 ms pulse of 0.5 nA into the soma, on top of a holding current of "
            "0.065 nA, in a 1500 ms simulation, and records the voltage in every section. "
            "Passes if the action potential is smaller at the furthest basal and apical "
            "dendrites than at the soma, and the soma fires exactly 1 spike over the whole "
            "simulation (threshold -20 mV)."
        )

    def test_bpap_without_spike_guard_scales_with_rheobase(self):
        test = BPAPTest(simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0))
        text = describe_test(test)
        assert "10 times the rheobase" in text
        assert "calibrated holding current" in text
        assert "fires exactly" not in text

    def test_iv_curve_uses_the_pinned_sweep(self):
        test = IVCurveTest(simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0))
        assert "5 steps from -1 to 0.9 times the rheobase" in describe_test(test)

    def test_fi_curve(self):
        test = FICurveTest(simulator_config=SimulatorConfig(celsius=34.0, v_init=-70.0))
        assert "5 steps from 1 to 3 times the rheobase" in describe_test(test)

    def test_test_without_description_is_not_described(self):
        class Undescribed(ValidationTest):
            @property
            def name(self):
                return "Undescribed"

            def run(self, template_params, rheobase, out_dir):
                _ = (template_params, rheobase, out_dir)
                return TestResult(name=self.name, passed=True, details="")

        assert not describe_test(Undescribed())


class TestProfileDescriptions:
    @pytest.mark.parametrize(
        "profile", [DefaultMEModelValidationProfile(), ThalamicMEModelValidationProfile()]
    )
    def test_every_profile_test_is_described(self, profile, tmp_path):
        for test in profile.build_tests(_thalamic_context(tmp_path)):
            assert describe_test(test), test.name

    def test_thalamic_thumbnail_describes_the_rebound_protocol(self, tmp_path):
        tests = ThalamicMEModelValidationProfile().build_tests(_thalamic_context(tmp_path))
        by_name = {test.name: test for test in tests}
        rebound = by_name["Rebound Burst Validation"]
        assert describe_test(by_name["thumbnail"]).startswith(describe_protocol(rebound.protocol))

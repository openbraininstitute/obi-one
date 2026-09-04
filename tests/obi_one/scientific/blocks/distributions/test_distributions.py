import math

import numpy as np
import pytest
from bluepyemodel.preprocessing.distributions import resolve_distance_dependent_distribution
from bluepyemodel.preprocessing.schemas import (
    STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS,
    LinearHDPasDistanceDependentDistribution,
)

import obi_one as obi
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import (
    EModelOptimizationScanConfig,
)


def _optimization_config(**overrides):
    config_data = {
        "info": {"campaign_name": "test", "campaign_description": "test"},
        "initialize": {"emodel": "test", "etype": {"id_str": "etype"}},
        "inputs": {
            "target_efeatures": {"id_str": "target"},
            "morphology": {"id_str": "morphology"},
        },
        "parameters_selection": {"ion_channel_models": [{"id_str": "icm"}]},
    }
    config_data.update(overrides)
    return EModelOptimizationScanConfig.model_validate(config_data)


class TestDistanceDependentDistributions:
    @pytest.mark.parametrize(
        ("distribution_class", "expected_name", "expected_function"),
        [
            (obi.UniformDistanceDependentDistribution, "uniform", None),
            (
                obi.ExponentialDistanceDependentDistribution,
                "exp",
                "(-0.8696 + 2.087*math.exp(({distance})*0.0031))*{value}",
            ),
            (
                obi.StepDistanceDependentDistribution,
                "step",
                (
                    "{value} * (0.1 + 0.9 * int(({distance} > {step_begin}) & "
                    "({distance} < {step_end})))"
                ),
            ),
            (
                obi.ExponentialNaDendDistanceDependentDistribution,
                "exp_na_dend",
                "math.exp((-{distance})/50)*{value}",
            ),
            (
                obi.LinearHDApicDistanceDependentDistribution,
                "linear_hd_apic",
                "(1. + 3./100. * {distance})*{value}",
            ),
            (
                obi.SigmoidKADApicDistanceDependentDistribution,
                "sigmoid_kad_apic",
                "(15./(1. + math.exp((300-{distance})/50)))*{value}",
            ),
            (
                obi.LinearEPasApicDistanceDependentDistribution,
                "linear_e_pas_apic",
                "({value}-5*{distance}/150)",
            ),
            (
                obi.LinearHDPasDistanceDependentDistribution,
                "linear_hdpas",
                "(1. + 3./100. * {distance})*{value}",
            ),
            (
                obi.SigmoidKADDistanceDependentDistribution,
                "sigmoid_kad",
                "(15./(1. + math.exp((150-{distance})/10)))*{value}",
            ),
            (
                obi.SigmoidKDBMApicDistanceDependentDistribution,
                "sigmoid_kdbm_apic",
                "(15./(1. + math.exp(({distance}-50)/50)))*{value}",
            ),
        ],
    )
    def test_legacy_distributions_serialize(
        self, distribution_class, expected_name, expected_function
    ):
        distribution = distribution_class()

        assert distribution.to_emc_dict() == {
            "name": expected_name,
            "function": expected_function,
            "soma_ref_location": 0.5,
        }

    def test_custom_distribution_is_validated_and_serialized(self):
        distribution = obi.CustomDistanceDependentDistribution(
            name="custom_profile",
            function="({value} + {distance}) / 2",
            soma_ref_location=0.25,
        )

        assert distribution.to_emc_dict() == {
            "name": "custom_profile",
            "function": "({value} + {distance}) / 2",
            "soma_ref_location": 0.25,
        }

    def test_custom_distribution_serializes_parameters(self):
        distribution = obi.CustomDistanceDependentDistribution(
            name="decay",
            function="math.exp({distance}*{constant})*{value}",
            parameters=["constant"],
        )

        assert distribution.to_emc_dict() == {
            "name": "decay",
            "function": "math.exp({distance}*{constant})*{value}",
            "soma_ref_location": 0.5,
            "parameters": ["constant"],
        }

    def test_empty_distribution_parameters_are_not_serialized(self):
        distribution = obi.CustomDistanceDependentDistribution(
            name="custom_profile",
            function="({value} + {distance}) / 2",
            parameters=[],
        )

        assert "parameters" not in distribution.to_emc_dict()

    def test_distribution_parameter_names_are_not_scan_dimensions(self):
        distribution = obi.CustomDistanceDependentDistribution(
            name="decay",
            function="math.exp({distance}*{constant})*{value}",
            parameters=["constant"],
        )

        assert distribution.parameters == ("constant",)
        assert distribution.multiple_value_parameters(category_name="distributions") == []

    def test_custom_distribution_requires_value_and_distance(self):
        with pytest.raises(ValueError, match=r"\{value\} placeholder"):
            obi.CustomDistanceDependentDistribution(name="custom", function="{distance}")

        with pytest.raises(ValueError, match=r"\{distance\} placeholder"):
            obi.CustomDistanceDependentDistribution(name="custom", function="{value}")

    def test_custom_distribution_requires_declared_parameters(self):
        with pytest.raises(ValueError, match=r"\{constant\} placeholder"):
            obi.CustomDistanceDependentDistribution(
                name="custom",
                function="math.exp({distance})*{value}",
                parameters=["constant"],
            )

    def test_distribution_parameters_require_a_function(self):
        with pytest.raises(ValueError, match="must define a function"):
            obi.DistanceDependentDistribution(parameters=["constant"])

    def test_standard_distributions_are_available_without_declaration(self):
        """The ten legacy distributions are selectable by name without being declared."""
        assert set(STANDARD_DISTANCE_DEPENDENT_DISTRIBUTIONS) == {
            "uniform",
            "exp",
            "step",
            "exp_na_dend",
            "linear_hd_apic",
            "sigmoid_kad_apic",
            "linear_e_pas_apic",
            "linear_hdpas",
            "sigmoid_kad",
            "sigmoid_kdbm_apic",
        }
        assert isinstance(
            resolve_distance_dependent_distribution("linear_hdpas", {}),
            LinearHDPasDistanceDependentDistribution,
        )

    def test_custom_distribution_declared_on_the_config_deserializes(self):
        config = _optimization_config(
            distance_dependent_distributions={
                "mouse_decay": {
                    "type": "CustomDistanceDependentDistribution",
                    "function": "math.exp({distance})*{value}",
                },
            }
        )

        assert isinstance(
            config.distance_dependent_distributions["mouse_decay"],
            obi.CustomDistanceDependentDistribution,
        )

    def test_optimization_parameter_selection_has_no_declared_distributions_by_default(self):
        config = _optimization_config()

        assert dict(config.distance_dependent_distributions) == {}

    def test_step_distribution_preserves_morphology_derived_placeholders(self):
        """BluePyEModel computes step_begin/step_end from the morphology hot-spot.

        They must not be required as user-declared ``parameters`` and must be
        preserved verbatim in the function string for BluePyEModel to substitute
        at runtime via ``get_hotspot_location()``.
        """
        distribution = obi.StepDistanceDependentDistribution()

        assert "{step_begin}" in distribution.function
        assert "{step_end}" in distribution.function
        assert distribution.parameters is None
        assert distribution.to_emc_dict() == {
            "name": "step",
            "function": (
                "{value} * (0.1 + 0.9 * int(({distance} > {step_begin}) & "
                "({distance} < {step_end})))"
            ),
            "soma_ref_location": 0.5,
        }


class TestFloatConstantDistribution:
    def test_sample_returns_repeated_scalar_values(self):
        """FloatConstantDistribution.sample() returns repeated scalar values, not nested lists."""
        dist = obi.FloatConstantDistribution(value=5.0)
        samples = dist.sample(n=3)
        assert samples == [5.0, 5.0, 5.0]
        assert all(isinstance(s, float) for s in samples)

    def test_sample_with_explicit_rng(self):
        """Passing an explicit numpy Generator to sample() works and is honored."""
        dist = obi.FloatConstantDistribution(value=math.pi)
        rng = np.random.default_rng(42)
        samples = dist.sample(n=2, rng=rng)
        assert samples == [math.pi, math.pi]

    def test_sample_is_concrete_and_usable(self):
        """Distribution.sample() is concrete and usable through subclasses."""
        dist = obi.FloatConstantDistribution(value=1.5)
        # Should not raise NotImplementedError
        result = dist.sample(n=1)
        assert result == [1.5]


class TestExponentialDistribution:
    def test_sample_returns_positive_float_samples(self):
        """ExponentialDistribution.sample() returns positive float samples."""
        dist = obi.ExponentialDistribution(scale=10.0, random_seed=42)
        samples = dist.sample(n=10)
        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s > 0 for s in samples)

    def test_sample_with_explicit_rng(self):
        """Passing an explicit numpy Generator to sample() works and is honored."""
        dist = obi.ExponentialDistribution(scale=5.0)
        rng = np.random.default_rng(123)
        samples1 = dist.sample(n=3, rng=rng)
        rng = np.random.default_rng(123)  # Reset seed
        samples2 = dist.sample(n=3, rng=rng)
        assert samples1 == samples2

    def test_sample_is_concrete_and_usable(self):
        """Distribution.sample() is concrete and usable through subclasses."""
        dist = obi.ExponentialDistribution(scale=1.0, random_seed=1)
        result = dist.sample(n=1)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] > 0

    def test_exponential_distribution_shift(self):
        dist = obi.ExponentialDistribution(scale=1.0, shift=5.0, random_seed=42)
        samples = dist.sample(10)

        assert all(sample >= 5.0 for sample in samples)

    def test_exponential_distribution_shift_adds_constant(self):
        base = obi.ExponentialDistribution(scale=1.0, random_seed=42)
        shifted = obi.ExponentialDistribution(scale=1.0, shift=5.0, random_seed=42)

        base_samples = base.sample(5)
        shifted_samples = shifted.sample(5)

        assert shifted_samples == [sample + 5.0 for sample in base_samples]


class TestGammaDistribution:
    def test_sample_returns_positive_float_samples(self):
        """GammaDistribution.sample() returns positive float samples."""
        dist = obi.GammaDistribution(shape=2.0, scale=5.0, random_seed=42)
        samples = dist.sample(n=10)
        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s > 0 for s in samples)

    def test_sample_with_explicit_rng(self):
        """Passing an explicit numpy Generator to sample() works and is honored."""
        dist = obi.GammaDistribution(shape=1.5, scale=2.0)
        rng = np.random.default_rng(456)
        samples1 = dist.sample(n=3, rng=rng)
        rng = np.random.default_rng(456)  # Reset seed
        samples2 = dist.sample(n=3, rng=rng)
        assert samples1 == samples2

    def test_sample_is_concrete_and_usable(self):
        """Distribution.sample() is concrete and usable through subclasses."""
        dist = obi.GammaDistribution(shape=1.0, scale=1.0, random_seed=1)
        result = dist.sample(n=1)
        assert len(result) == 1
        assert isinstance(result[0], float)
        assert result[0] > 0

    def test_gamma_distribution_shift(self):
        dist = obi.GammaDistribution(shape=2.0, scale=1.0, shift=5.0, random_seed=42)
        samples = dist.sample(10)

        assert all(sample >= 5.0 for sample in samples)


class TestDistributionConstraints:
    def test_constraint_validation_ge_gt(self):
        """Constraint validation raises for both ge and gt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="Only one of ge and gt can be specified"):
            dist.sample(n=1, ge=0.5, gt=0.5)

    def test_constraint_validation_le_lt(self):
        """Constraint validation raises for both le and lt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="Only one of le and lt can be specified"):
            dist.sample(n=1, le=2.0, lt=2.0)

    def test_constraint_validation_ge_le_inconsistent(self):
        """Constraint validation raises for ge > le."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="ge must be less than or equal to le"):
            dist.sample(n=1, ge=2.0, le=1.0)

    def test_constraint_validation_gt_lt_inconsistent(self):
        """Constraint validation raises for gt >= lt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="gt must be less than lt"):
            dist.sample(n=1, gt=2.0, lt=2.0)

    def test_constraint_validation_ge_lt_inconsistent(self):
        """Constraint validation raises for ge > lt."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="ge must be less than or equal to lt"):
            dist.sample(n=1, ge=2.0, lt=1.5)

    def test_constraint_validation_gt_le_inconsistent(self):
        """Constraint validation raises for gt >= le."""
        dist = obi.FloatConstantDistribution(value=1.0)
        with pytest.raises(ValueError, match="gt must be less than le"):
            dist.sample(n=1, gt=2.0, le=2.0)


class TestNormalDistribution:
    def test_sample_returns_float_samples(self):
        dist = obi.NormalDistribution(
            mean=0.0,
            standard_deviation=1.0,
            random_seed=42,
        )

        samples = dist.sample(n=10)

        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)

    def test_sample_with_explicit_rng(self):
        dist = obi.NormalDistribution(
            mean=0.0,
            standard_deviation=1.0,
        )

        rng = np.random.default_rng(123)
        samples1 = dist.sample(n=3, rng=rng)

        rng = np.random.default_rng(123)
        samples2 = dist.sample(n=3, rng=rng)

        assert samples1 == samples2


class TestLogNormalDistribution:
    def test_sample_returns_positive_float_samples(self):
        dist = obi.LogNormalDistribution(
            mean=0.0,
            sigma=1.0,
            random_seed=42,
        )

        samples = dist.sample(n=10)

        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s > 0 for s in samples)

    def test_sample_with_explicit_rng(self):
        dist = obi.LogNormalDistribution(
            mean=0.0,
            sigma=1.0,
        )

        rng = np.random.default_rng(456)
        samples1 = dist.sample(n=3, rng=rng)

        rng = np.random.default_rng(456)
        samples2 = dist.sample(n=3, rng=rng)

        assert samples1 == samples2


class TestPoissonDistribution:
    def test_sample_returns_non_negative_integer_like_samples(self):
        dist = obi.PoissonDistribution(
            rate=5.0,
            random_seed=42,
        )

        samples = dist.sample(n=10)

        assert len(samples) == 10
        assert all(isinstance(s, float) for s in samples)
        assert all(s >= 0 for s in samples)
        assert all(float(s).is_integer() for s in samples)

    def test_sample_with_explicit_rng(self):
        dist = obi.PoissonDistribution(
            rate=5.0,
        )

        rng = np.random.default_rng(789)
        samples1 = dist.sample(n=3, rng=rng)

        rng = np.random.default_rng(789)
        samples2 = dist.sample(n=3, rng=rng)

        assert samples1 == samples2

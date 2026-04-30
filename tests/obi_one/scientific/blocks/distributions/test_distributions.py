import math

import numpy as np
import pytest

import obi_one as obi


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

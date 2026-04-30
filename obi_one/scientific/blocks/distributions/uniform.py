from typing import ClassVar

import numpy as np
from pydantic import (
    Field,
)

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class UniformDistribution(Distribution):
    """Uniform distribution."""

    low: float | list[float] = Field(
        default=0.0,
        title="Low",
        description="The lower bound of the uniform distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    high: float | list[float] = Field(
        default=1.0,
        title="High",
        description="The upper bound of the uniform distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description=("Seed for drawing random values from the uniform distribution."),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )


class FloatUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of floats."""

    title: ClassVar[str] = "Uniform Floats"

    def _sample_generator(self, n: int = 1, rng: np.random.Generator | None = None) -> list[float]:
        """Sample n values from the uniform distribution."""
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.uniform(low=self.low, high=self.high, size=n)
        return samples.tolist()


class IntUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of integers."""

    title: ClassVar[str] = "Uniform Integers"

    def _sample_generator(self, n: int = 1, rng: np.random.Generator | None = None) -> list[float]:
        """Sample n values from the uniform distribution.

        Don't worry about the constraints here, since the sample method will handle them.
        """
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.integers(low=self.low, high=self.high, size=n)  # ty:ignore[no-matching-overload]
        return samples.astype(float).tolist()

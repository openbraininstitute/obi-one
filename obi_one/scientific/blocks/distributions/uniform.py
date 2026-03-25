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

    value: float | list[float] = Field(
        default=1.0,
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def sample(self, n: int = 1) -> list[float]:
        """Sample n values from the uniform distribution."""
        rng = np.random.default_rng(self.random_seed)
        samples = rng.uniform(low=self.low, high=self.high, size=n)
        return samples.tolist()


class IntUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of integers."""

    title: ClassVar[str] = "Uniform Integers"

    value: int | list[int] = Field(
        default=1,
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def sample(
        self,
        n: int = 1,
        ge: int | None = None,
        le: int | None = None,
        gt: int | None = None,
        lt: int | None = None,
    ) -> list[int]:
        """Sample n values from the uniform distribution."""
        rng = np.random.default_rng(self.random_seed)
        samples = rng.integers(low=self.low, high=self.high, size=n)

        if ge is not None:
            samples = [max(s, ge) for s in samples]
        if le is not None:
            samples = [min(s, le) for s in samples]
        if gt is not None:
            samples = [s for s in samples if s > gt]
        if lt is not None:
            samples = [s for s in samples if s < lt]

        return samples.tolist()

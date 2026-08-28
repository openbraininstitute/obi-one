from typing import ClassVar

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class FloatUniformDistribution(Distribution):
    """Samples floating-point values uniformly between a lower and upper bound."""

    title: ClassVar[str] = "Uniform Floats"

    low: float | list[float] = Field(
        default=0.0,
        title="Low",
        description="Lower endpoint of the uniform sampling interval.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    high: float | list[float] = Field(
        default=1.0,
        title="High",
        description="Upper endpoint of the uniform sampling interval.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description="Seed for reproducible sampling.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def _sample_generator(
        self,
        n: int = 1,
        rng: np.random.Generator | None = None,
    ) -> list[float]:
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.uniform(low=self.low, high=self.high, size=n)
        return samples.tolist()


class IntUniformDistribution(Distribution):
    """Samples integer values uniformly from a lower-inclusive, upper-exclusive interval."""

    title: ClassVar[str] = "Uniform Integers"

    low: int | list[int] = Field(
        default=0,
        title="Low",
        description="Inclusive lower endpoint of the integer sampling interval.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    high: int | list[int] = Field(
        default=1,
        title="High",
        description="Exclusive upper endpoint of the integer sampling interval.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )
    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description="Seed for reproducible sampling.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def _sample_generator(
        self,
        n: int = 1,
        rng: np.random.Generator | None = None,
    ) -> list[float]:
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.integers(low=self.low, high=self.high, size=n)
        return samples.astype(float).tolist()

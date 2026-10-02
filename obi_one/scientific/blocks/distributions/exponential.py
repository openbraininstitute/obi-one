from typing import ClassVar

import numpy as np
from pydantic import Field, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class ExponentialDistribution(Distribution):
    """Samples non-negative values from an exponential distribution with an optional shift."""

    title: ClassVar[str] = "Exponential"

    scale: PositiveFloat | list[PositiveFloat] = Field(
        default=50.0,
        title="Scale",
        description="Scale parameter controlling the spread of the exponential samples.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    shift: float | list[float] = Field(
        default=0.0,
        title="Shift",
        description="Constant offset added to each generated sample.",
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

    def _sample_generator(self, n: int = 1, rng: np.random.Generator | None = None) -> list[float]:
        """Sample n values from the exponential distribution."""
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.exponential(scale=self.scale, size=n) + self.shift
        return samples.tolist()

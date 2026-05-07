from typing import ClassVar

import numpy as np
from pydantic import Field, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.units import Units
from obi_one.scientific.blocks.distributions.base import Distribution


class GammaDistribution(Distribution):
    """Values sampled from a gamma distribution."""

    title: ClassVar[str] = "Gamma"

    shape: PositiveFloat | list[PositiveFloat] = Field(
        default=2.0,
        title="Shape",
        description="Shape parameter of the gamma distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )
    scale: PositiveFloat | list[PositiveFloat] = Field(
        default=25.0,
        title="Scale",
        description="Scale parameter of the gamma distribution in milliseconds."
        "Mean ISI = shape x scale.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    shift: float | list[float] = Field(
        default=0.0,
        title="Shift",
        description="Constant value added to each sampled value.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
            SchemaKey.UNITS: Units.MILLISECONDS,
        },
    )
    random_seed: int | list[int] = Field(
        default=1,
        title="Random Seed",
        description="Seed for drawing random values from the gamma distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def _sample_generator(self, n: int = 1, rng: np.random.Generator | None = None) -> list[float]:
        """Sample n values from the gamma distribution."""
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.gamma(shape=self.shape, scale=self.scale, size=n) + self.shift
        return samples.tolist()

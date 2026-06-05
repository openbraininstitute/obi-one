from typing import ClassVar

import numpy as np
from pydantic import Field, PositiveFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class NormalDistribution(Distribution):
    """Values sampled from a normal distribution."""

    title: ClassVar[str] = "Normal"

    mean: float | list[float] = Field(
        default=0.0,
        title="Mean",
        description="Mean of the normal distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    standard_deviation: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Standard Deviation",
        description="Standard deviation of the normal distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    random_seed: int | list[int] = Field(
        default=1,
        title="Random Seed",
        description="Seed for drawing random values from the normal distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def _sample_generator(
        self,
        n: int = 1,
        rng: np.random.Generator | None = None,
    ) -> list[float]:
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.normal(loc=self.mean, scale=self.standard_deviation, size=n)
        return samples.tolist()

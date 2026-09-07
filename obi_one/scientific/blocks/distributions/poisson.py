from typing import ClassVar

import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class PoissonDistribution(Distribution):
    """Samples non-negative integer event counts from a Poisson distribution."""

    title: ClassVar[str] = "Poisson"

    rate: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=1.0,
        title="Event Rate",
        description="Expected event count represented by the distribution.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description="Seed for reproducible sampling.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP},
    )

    def _sample_generator(
        self,
        n: int = 1,
        rng: np.random.Generator | None = None,
    ) -> list[float]:
        if rng is None:
            rng = np.random.default_rng(self.random_seed)
        samples = rng.poisson(lam=self.rate, size=n)
        return samples.astype(float).tolist()

from typing import ClassVar

import numpy as np
from pydantic import Field, NonNegativeFloat

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class PoissonDistribution(Distribution):
    """Values sampled from a Poisson distribution."""

    title: ClassVar[str] = "Poisson"

    rate: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=1.0,
        title="Event Rate",
        description="Average event occurrence rate for the sampled interval.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP},
    )
    random_seed: int | list[int] = Field(
        default=1,
        title="Random Seed",
        description="Seed for drawing random values from the Poisson distribution.",
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

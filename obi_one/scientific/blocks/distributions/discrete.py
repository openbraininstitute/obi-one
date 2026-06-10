from typing import ClassVar

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class IntDiscreteDistribution(Distribution):
    """A distribution with discrete, explicitly parameterized probabilities."""

    title: ClassVar[str] = "Discrete Integer"

    values: tuple[int, ...] | list[tuple[int, ...]] = Field(
        default=(1,),
        title="Values",
        description="The possible values of the distribution.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )
    probabilities: tuple[float, ...] | list[tuple[float, ...]] = Field(
        default=(1.0,),
        title="Probabilities",
        description="Probabilities for the discrete values of the distribution.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    random_seed: int | list[int] = Field(
        default=1,
        title="Random Seed",
        description="Seed for drawing random values from the exponential distribution.",
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
        p = np.array(self.probabilities)
        p /= p.sum()
        return list(rng.choice(self.values, size=n, replace=True, p=p))

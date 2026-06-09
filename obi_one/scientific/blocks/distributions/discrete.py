from typing import ClassVar

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class IntDiscreteDistribution(Distribution):
    """A distribution with discrete, explicitly parameterized probabilities."""

    title: ClassVar[str] = "Constant Float"

    values: tuple[int, ...] | list[tuple[int, ...]] = Field(
        default=(1,),
        title="Values",
        description="The possible values of the distribution."
    )
    probabilities: tuple[float, ...] | list[tuple[float, ...]] = Field(
        default=(1.0,),
        title="Probabilities",
        description="Probabilities for the discrete values of the distribution."
    )

    def _sample_generator(
        self,
        n: int = 1,
        rng: np.random.Generator | None = None,  # noqa: ARG002
    ) -> list[float]:
        p = np.array(self.probabilities)
        p = p / p.sum()
        return list(np.random.choice(self.values, size=n,
                                     replace=True, p=p))

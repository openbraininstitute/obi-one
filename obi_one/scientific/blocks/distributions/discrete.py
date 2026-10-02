from typing import ClassVar, Self

import numpy as np
from pydantic import Field, model_validator

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class IntDiscreteDistribution(Distribution):
    """Samples explicitly listed integer values using configured probabilities."""

    title: ClassVar[str] = "Discrete Integer"

    # `values` carries the UI element and `probabilities` is hidden because the two are one
    # control: a table of value/probability rows, edited together. Two independent list editors
    # would let them drift to different lengths, which is the one thing the pair cannot be.
    #
    # Neither is sweepable. A sweep needs a list of whole tuples, which reads in the schema as
    # exactly the same shape as a single tuple of values, so a UI could not tell "these are my
    # five values" from "these are five separate configurations to run".
    values: tuple[int, ...] = Field(
        default=(1,),
        title="Values",
        description="Possible integer values to sample.",
        json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.DISCRETE_PROBABILITIES},
    )
    probabilities: tuple[float, ...] = Field(
        default=(1.0,),
        title="Probabilities",
        description="Sampling probability for each possible value. Normalized before sampling.",
        json_schema_extra={SchemaKey.UI_HIDDEN: True},
    )

    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description="Seed for reproducible sampling.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    @model_validator(mode="after")
    def _values_and_probabilities_agree(self) -> Self:
        """Reject a pair that `_sample_generator` could not use.

        These were unreachable while both fields were hidden from the UI - only code built
        one, and only with matching arrays. Now that a person can edit them, each of these is
        a mistake somebody can make, and every one of them fails inside numpy with a message
        that names neither field.
        """
        if not self.values:
            msg = "A discrete distribution needs at least one value to sample."
            raise ValueError(msg)
        if len(self.values) != len(self.probabilities):
            msg = (
                f"Each value needs its own probability: got {len(self.values)} values "
                f"({self.values}) and {len(self.probabilities)} probabilities "
                f"({self.probabilities})."
            )
            raise ValueError(msg)
        if any(probability < 0 for probability in self.probabilities):
            msg = f"Probabilities cannot be negative; got {self.probabilities}."
            raise ValueError(msg)
        if sum(self.probabilities) <= 0:
            # They are normalized below, so they need not sum to 1 - but they cannot all be
            # zero, which would leave no value able to be drawn.
            msg = f"At least one probability must be above zero; got {self.probabilities}."
            raise ValueError(msg)
        return self

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

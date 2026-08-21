from typing import ClassVar

import numpy as np
from pydantic import Field

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class FloatConstantDistribution(Distribution):
    """Produces the same floating-point value for every sample."""

    title: ClassVar[str] = "Constant Float"

    value: float | list[float] = Field(
        default=1.0,
        title="Value",
        description="Value returned for each sample.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def _sample_generator(
        self,
        n: int = 1,
        rng: np.random.Generator | None = None,  # ruff: ignore[unused-method-argument]
    ) -> list[float]:
        if isinstance(self.value, list):
            return [float(v) for v in self.value][:n]
        return [float(self.value)] * n


class IntConstantDistribution(Distribution):
    """Produces the same integer value for every sample."""

    title: ClassVar[str] = "Constant Integer"

    value: int | list[int] = Field(
        default=1,
        title="Value",
        description="Value returned for each sample.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def _sample_generator(
        self,
        n: int = 1,
        rng: np.random.Generator | None = None,  # ruff: ignore[unused-method-argument]
    ) -> list[float]:
        if isinstance(self.value, list):
            return [float(v) for v in self.value][:n]
        return [float(self.value)] * n

from typing import ClassVar

from pydantic import (
    Field,
)

from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.blocks.distributions.base import Distribution


class FloatConstantDistribution(Distribution):
    """A single float value."""

    title: ClassVar[str] = "Constant Float"

    value: float | list[float] = Field(
        default=1.0,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )

    def sample(self, n: int = 1) -> list[float]:
        """Sample n values from the distribution."""
        return [self.value] * n


class IntConstantDistribution(Distribution):
    """A single integer value."""

    title: ClassVar[str] = "Constant Integer"

    value: int | list[int] = Field(
        default=1,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

    def sample(self, n: int = 1) -> list[int]:
        """Sample n values from the distribution."""
        return [self.value] * n

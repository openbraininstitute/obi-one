from typing import ClassVar

from pydantic import (
    Field,
    NegativeFloat,
    NegativeInt,
    NonNegativeFloat,
    NonNegativeInt,
    NonPositiveFloat,
    NonPositiveInt,
    PositiveFloat,
    PositiveInt,
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


class PositiveFloatConstantDistribution(Distribution):
    """A single positive float value."""

    title: ClassVar[str] = "Constant Positive Float"

    value: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )


class PositiveIntConstantDistribution(Distribution):
    """A single positive integer value."""

    title: ClassVar[str] = "Constant Positive Integer"

    value: PositiveInt | list[PositiveInt] = Field(
        default=1,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )


class NegativeFloatConstantDistribution(Distribution):
    """A single negative float value."""

    title: ClassVar[str] = "Constant Negative Float"

    value: NegativeFloat | list[NegativeFloat] = Field(
        default=-1.0,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )


class NegativeIntConstantDistribution(Distribution):
    """A single negative integer value."""

    title: ClassVar[str] = "Constant Negative Integer"

    value: NegativeInt | list[NegativeInt] = Field(
        default=-1,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )


class NonNegativeFloatConstantDistribution(Distribution):
    """A single non-negative float value."""

    title: ClassVar[str] = "Constant Non-Negative Float"

    value: NonNegativeFloat | list[NonNegativeFloat] = Field(
        default=1.0,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )


class NonNegativeIntConstantDistribution(Distribution):
    """A single non-negative integer value."""

    title: ClassVar[str] = "Constant Non-Negative Integer"

    value: NonNegativeInt | list[NonNegativeInt] = Field(
        default=1,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )


class NonPositiveFloatConstantDistribution(Distribution):
    """A single non-positive float value."""

    title: ClassVar[str] = "Constant Non-Positive Float"

    value: NonPositiveFloat | list[NonPositiveFloat] = Field(
        default=-1.0,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
        },
    )


class NonPositiveIntConstantDistribution(Distribution):
    """A single non-positive integer value."""

    title: ClassVar[str] = "Constant Non-Positive Integer"

    value: NonPositiveInt | list[NonPositiveInt] = Field(
        default=-1,
        title="Value",
        description="The constant value of the distribution.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.INT_PARAMETER_SWEEP,
        },
    )

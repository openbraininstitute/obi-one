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

from obi_one.scientific.blocks.distributions.base import Distribution


class UniformDistribution(Distribution):
    """Uniform distribution."""

    low: float | list[float] = Field(
        default=0.0,
        title="Low",
        description="The lower bound of the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )
    high: float | list[float] = Field(
        default=1.0,
        title="High",
        description="The upper bound of the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )

    random_seed: int | list[int] = Field(
        default=1,
        title="Random seed",
        description=("Seed for drawing random values from the uniform distribution."),
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class FloatUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of floats."""

    title: ClassVar[str] = "Uniform Floats"

    value: float | list[float] = Field(
        default=1.0,
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class IntUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of integers."""

    title: ClassVar[str] = "Uniform Integers"

    value: int | list[int] = Field(
        default=1,
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class PositiveFloatUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of positive floats."""

    value: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class PositiveIntUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of positive integers."""

    title: ClassVar[str] = "Uniform Positive Integers"

    value: PositiveInt | list[PositiveInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class NegativeFloatUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of negative floats."""

    title: ClassVar[str] = "Uniform Negative Floats"

    value: NegativeFloat | list[NegativeFloat] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class NegativeIntUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of negative integers."""

    title: ClassVar[str] = "Uniform Negative Integers"

    value: NegativeInt | list[NegativeInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class NonNegativeFloatUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of non-negative floats."""

    title: ClassVar[str] = "Uniform Non-Negative Floats"

    value: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class NonNegativeIntUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of non-negative integers."""

    title: ClassVar[str] = "Uniform Non-Negative Integers"

    value: NonNegativeInt | list[NonNegativeInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class NonPositiveFloatUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of non-positive floats."""

    title: ClassVar[str] = "Uniform Non-Positive Floats"

    value: NonPositiveFloat | list[NonPositiveFloat] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class NonPositiveIntUniformDistribution(UniformDistribution):
    """Values sampled from a uniform distribution of non-positive integers."""

    title: ClassVar[str] = "Uniform Non-Positive Integers"

    value: NonPositiveInt | list[NonPositiveInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )

from typing import ClassVar

import numpy as np
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

    def sample(self, n: int = 1) -> list[float]:
        """Sample n values from the uniform distribution."""
        rng = np.random.default_rng(self.random_seed)
        samples = rng.uniform(low=self.low, high=self.high, size=n)
        return samples.tolist()


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

    def sample(self, n: int = 1) -> list[int]:
        """Sample n values from the uniform distribution."""
        rng = np.random.default_rng(self.random_seed)
        samples = rng.integers(low=self.low, high=self.high, size=n)
        return samples.tolist()


class PositiveFloatUniformDistribution(FloatUniformDistribution):
    """Values sampled from a uniform distribution of positive floats."""

    value: PositiveFloat | list[PositiveFloat] = Field(
        default=1.0,
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class PositiveIntUniformDistribution(IntUniformDistribution):
    """Values sampled from a uniform distribution of positive integers."""

    title: ClassVar[str] = "Uniform Positive Integers"

    value: PositiveInt | list[PositiveInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class NegativeFloatUniformDistribution(FloatUniformDistribution):
    """Values sampled from a uniform distribution of negative floats."""

    title: ClassVar[str] = "Uniform Negative Floats"

    value: NegativeFloat | list[NegativeFloat] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class NegativeIntUniformDistribution(IntUniformDistribution):
    """Values sampled from a uniform distribution of negative integers."""

    title: ClassVar[str] = "Uniform Negative Integers"

    value: NegativeInt | list[NegativeInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class NonNegativeFloatUniformDistribution(FloatUniformDistribution):
    """Values sampled from a uniform distribution of non-negative floats."""

    title: ClassVar[str] = "Uniform Non-Negative Floats"

    value: NonNegativeFloat | list[NonNegativeFloat] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class NonNegativeIntUniformDistribution(IntUniformDistribution):
    """Values sampled from a uniform distribution of non-negative integers."""

    title: ClassVar[str] = "Uniform Non-Negative Integers"

    value: NonNegativeInt | list[NonNegativeInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )


class NonPositiveFloatUniformDistribution(FloatUniformDistribution):
    """Values sampled from a uniform distribution of non-positive floats."""

    title: ClassVar[str] = "Uniform Non-Positive Floats"

    value: NonPositiveFloat | list[NonPositiveFloat] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )


class NonPositiveIntUniformDistribution(IntUniformDistribution):
    """Values sampled from a uniform distribution of non-positive integers."""

    title: ClassVar[str] = "Uniform Non-Positive Integers"

    value: NonPositiveInt | list[NonPositiveInt] = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        json_schema_extra={
            "ui_element": "int_parameter_sweep",
        },
    )

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

    low: float = Field(
        title="Low",
        description="The lower bound of the uniform distribution.",
    )
    high: float = Field(
        title="High",
        description="The upper bound of the uniform distribution.",
    )

    random_seed: int | None = Field(
        default=None,
        title="Random seed",
        description=(
            "Seed for drawing random values from the uniform distribution. If None, a random seed "
            "will be generated automatically."
        ),
    )


class FloatUniformDistribution(UniformDistribution):
    value: float = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="float_parameter_sweep",
    )


class IntegerUniformDistribution(UniformDistribution):
    value: int = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="int_parameter_sweep",
    )


class PositiveUniformDistribution(UniformDistribution):
    value: PositiveFloat = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="float_parameter_sweep",
    )


class NonNegativeUniformDistribution(UniformDistribution):
    value: NonNegativeFloat = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="float_parameter_sweep",
    )


class NegativeUniformDistribution(UniformDistribution):
    value: NegativeFloat = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="float_parameter_sweep",
    )


class NonPositiveUniformDistribution(UniformDistribution):
    value: NonPositiveFloat = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="float_parameter_sweep",
    )


class PositiveIntegerUniformDistribution(UniformDistribution):
    value: PositiveInt = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="int_parameter_sweep",
    )


class NonNegativeIntegerUniformDistribution(UniformDistribution):
    value: NonNegativeInt = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="int_parameter_sweep",
    )


class NegativeIntegerUniformDistribution(UniformDistribution):
    value: NegativeInt = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="int_parameter_sweep",
    )


class NonPositiveIntegerUniformDistribution(UniformDistribution):
    value: NonPositiveInt = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="int_parameter_sweep",
    )

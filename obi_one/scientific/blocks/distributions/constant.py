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


class FloatConstantDistribution(Distribution):
    """Constant distribution."""

    value: float = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="float_parameter_sweep",
    )


class IntegerConstantDistribution(Distribution):
    """Constant distribution."""

    value: int = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="int_parameter_sweep",
    )


class PositiveConstantDistribution(Distribution):
    """Constant distribution."""

    value: PositiveFloat = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="float_parameter_sweep",
    )


class NonNegativeConstantDistribution(Distribution):
    """Constant distribution."""

    value: NonNegativeFloat = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="float_parameter_sweep",
    )


class NegativeConstantDistribution(Distribution):
    """Constant distribution."""

    value: NegativeFloat = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="float_parameter_sweep",
    )


class NonPositiveConstantDistribution(Distribution):
    """Constant distribution."""

    value: NonPositiveFloat = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="float_parameter_sweep",
    )


class PositiveIntegerConstantDistribution(Distribution):
    """Constant distribution."""

    value: PositiveInt = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="int_parameter_sweep",
    )


class NonNegativeIntegerConstantDistribution(Distribution):
    """Constant distribution."""

    value: NonNegativeInt = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="int_parameter_sweep",
    )


class NegativeIntegerConstantDistribution(Distribution):
    """Constant distribution."""

    value: NegativeInt = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="int_parameter_sweep",
    )


class NonPositiveIntegerConstantDistribution(Distribution):
    """Constant distribution."""

    value: NonPositiveInt = Field(
        title="Value",
        description="The constant value of the distribution.",
        ui_element="int_parameter_sweep",
    )

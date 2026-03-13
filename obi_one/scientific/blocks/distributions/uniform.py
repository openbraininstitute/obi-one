from pydantic import Field

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

    value: float = Field(
        title="Value",
        description="The value sampled from the uniform distribution.",
        ui_element="float_parameter_sweep",
    )

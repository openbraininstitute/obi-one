from pydantic import Field

from obi_one.core.block import Block


class SynapseParameterization(Block):
    overwrite_if_exists: bool = Field(
        title="Overwrite",
        description="Overwrite if a parameterization exists already.",
        default=False,
    )

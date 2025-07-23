from pydantic import Field

from obi_one.core.block import Block


class Info(Block):
    campaign_name: str = Field(min_length=1, description="Name of the simulation campaign.")
    campaign_description: str = Field(
        min_length=1, description="Description of the simulation campaign."
    )

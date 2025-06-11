
from obi_one.core.block import Block
from pydantic import Field

class Info(Block):
    campaign_name: str = Field(default="No name provided", description="The users name for the simulation")
    campaign_description: str = Field(default="No description provided", description="Description of the simulation")
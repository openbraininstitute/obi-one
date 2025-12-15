from pydantic import Field

from obi_one.core.block import Block


class Info(Block):
    campaign_name: str = Field(min_length=1, description="Name of the campaign.")
    campaign_description: str = Field(min_length=1, description="Description of the campaign.")

    class Config:
        title = "Information"
        group = "test"
        group_order = 0
        json_schema_extra = {
            "title": "Title of the Block",
            "ui_enabled": True,
            "description": "description of the block",
            "group": "Group 1",
            "group_order": 0,
            "ui_element": 'root_block'
        }

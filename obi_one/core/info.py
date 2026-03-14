from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import UIElement


class Info(Block):
    campaign_name: str = Field(
        min_length=1,
        description="Name of the campaign.",
        json_schema_extra={"ui_element": UIElement.STRING_INPUT},
    )
    campaign_description: str = Field(
        min_length=1,
        description="Description of the campaign.",
        json_schema_extra={"ui_element": UIElement.STRING_INPUT},
    )

from enum import StrEnum

from pydantic import Field

from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement


class BlockGroup(StrEnum):
    SETUP_BLOCK_GROUP = "Setup"


class InfoScanConfig(ScanConfig):
    info: Info = Field(
        title="Info",
        description="Information about the campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    @property
    def campaign_name(self) -> str:
        return self.info.campaign_name

    @property
    def campaign_description(self) -> str:
        return self.info.campaign_description

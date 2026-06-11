from pydantic import BaseModel, ConfigDict, Field

from obi_one.scientific.library.entity_property_types import (
    MorphologySourceMappedProperties,
)


class MorphologySectionTypeOption(BaseModel):
    value: int
    label: str


class MorphologySourceProperties(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    section_types: list[MorphologySectionTypeOption] = Field(
        alias=MorphologySourceMappedProperties.SECTION_TYPES
    )
    usability: dict[str, bool] = Field(default_factory=dict)

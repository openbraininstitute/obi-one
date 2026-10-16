from enum import StrEnum
from typing import ClassVar

from entitysdk import Client
from entitysdk.models import Entity
from entitysdk.types import EntityType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.emodel_from_id import EModelFromID
from obi_one.scientific.library.info_scan_config.config import (
    BlockGroup as InfoBlockGroup,
    InfoScanConfig,
)


class BlockGroup(StrEnum):
    INPUTS = "Inputs"


class MEModelBuildScanConfig(InfoScanConfig):
    """Combine one morphology and one e-model into an ME-model, then calibrate and validate it.

    The campaign name and description become the ME-model's name and description. Species,
    strain and brain region come from the morphology.
    """

    name: ClassVar[str] = "ME-model Build"
    description: ClassVar[str] = (
        "Combine a morphology and an e-model into an ME-model, then calibrate and validate it."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [InfoBlockGroup.SETUP_BLOCK_GROUP, BlockGroup.INPUTS],
    }

    class Initialize(Block):
        title: ClassVar[str] = "ME-model inputs"

        morphology: CellMorphologyFromID = Field(
            title="Morphology",
            description="Cell morphology of the ME-model. Its species, strain and brain region "
            "are given to the ME-model.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
                SchemaKey.ENTITY_QUERY: {"type": EntityType.cell_morphology},
            },
        )
        emodel: EModelFromID = Field(
            title="E-model",
            description="Electrical model placed on the morphology.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_SELECTOR_SINGLE,
                SchemaKey.ENTITY_QUERY: {"type": EntityType.emodel},
            },
        )

    initialize: Initialize = Field(
        title="ME-model inputs",
        description="Morphology and e-model the ME-model is built from.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.INPUTS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    def input_entities(self, db_client: Client) -> list[Entity]:
        return [
            self.initialize.morphology.entity(db_client=db_client),
            self.initialize.emodel.entity(db_client=db_client),
        ]


class MEModelBuildSingleConfig(MEModelBuildScanConfig, SingleConfigMixin):
    """Single-coordinate variant of :class:`MEModelBuildScanConfig`."""

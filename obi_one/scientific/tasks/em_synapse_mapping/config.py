import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.types import EntityType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"


class EMSynapseMappingScanConfig(ScanConfig):
    name: ClassVar[str] = "Map synapse locations"
    description: ClassVar[str] = "Map location of afferent synapses from EM onto a spiny morphology"

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [
            BlockGroup.SETUP_BLOCK_GROUP,
        ],
    }

    class Initialize(Block):
        spiny_neuron: CellMorphologyFromID = Field(  # | MEModelFromID
            title="EM skeletonized morphology",
            description="""A neuron morphology with spines obtained from an electron-microscopy
            datasets through the skeletonization task.""",
            json_schema_extra={
                "ui_element": "model_selector_single",
                "entity_query": {
                    "type": EntityType.cell_morphology_from_id,
                    "filters": {
                        "cell_morphology_protocol": "ultraliser",
                    },
                },
            },
        )
        edge_population_name: str = Field(
            default="afferent_synapses",
            min_length=1,
            title="Edge population name",
            description="Name of the edge population to write the synapse information into",
            json_schema_extra={
                "ui_element": "string_input",
            },
        )
        node_population_pre: str = Field(
            default="afferent_neurons",
            min_length=1,
            title="Presynaptic node population name",
            description="""Name of the node population to write the information about the
            innervating neurons into""",
            json_schema_extra={
                "ui_element": "string_input",
            },
        )
        node_population_post: str = Field(
            default="biophysical_neuron",
            min_length=1,
            title="Postsynaptic node population name",
            description="""Name of the node population to write the information about the
            synaptome neuron into""",
            json_schema_extra={
                "ui_element": "string_input",
            },
        )

    info: Info = Field(  # type: ignore[]
        title="Info",
        description="Information about ...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 0,
        },
    )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing...",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 1,
        },
    )

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> Config:
        self._campaign = db_client.register_entity(
            entitysdk.models.SimulationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                entity_id=entity_id,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SimulationCampaign,
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type="application/json",
            asset_label="campaign_generation_config",
        )

        return self._campaign

    def create_campaign_generation_entity(
        self, simulations: list[entitysdk.models.Simulation], db_client: entitysdk.client.Client
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SimulationGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=simulations,
            )
        )


class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
    pass

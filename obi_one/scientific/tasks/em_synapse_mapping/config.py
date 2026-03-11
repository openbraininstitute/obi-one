import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

import entitysdk
from entitysdk.types import ActivityStatus, AssetLabel, EntityType, TaskConfigType
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.library.constants import _SCAN_CONFIG_FILENAME

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

    def input_entity_ids(self):
        return [self.initialize.spiny_neuron.id_str]

    def create_campaign_entity_with_config(
        self,
        output_root: Path,
        multiple_value_parameters_dictionary: dict | None = None,
        db_client: entitysdk.client.Client = None,
    ) -> entitysdk.models.TaskConfig:
        
        L.info("-- Create campaign TaskConfig entity")
        self._campaign = db_client.register_entity(
            entitysdk.models.TaskConfig(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                task_config_type=TaskConfigType.em_synapse_mapping__campaign,
                meta={"scan_parameters": multiple_value_parameters_dictionary},
                inputs=[entitysdk.models.Entity(id=entity_id) for entity_id in self.input_entity_ids()],
            )
        )

        L.info("-- Upload task_config asset for campaign TaskConfig")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.TaskConfig,
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type="application/json",
            asset_label=AssetLabel.task_config,
        )

        return self._campaign

    def create_campaign_generation_entity(
        self, generated: list[entitysdk.models.TaskConfig], db_client: entitysdk.client.Client
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.TaskActivity(
                task_activity_type=TaskConfigType.em_synapse_mapping__config_generation,
                status=ActivityStatus.completed,
                start_time=datetime.now(UTC),
                end_time=datetime.now(UTC),
                used=[self._campaign],
                generated=generated,
            )
        )

class EMSynapseMappingSingleConfig(EMSynapseMappingScanConfig, SingleConfigMixin):
    
    _single_entity: models.CircuitExtractionConfig = None

    @property
    def single_entity(self) -> models.CircuitExtractionConfig:
        return self._single_entity

    def set_single_entity(self, entity: models.CircuitExtractionConfig) -> None:
        """Sets the single entity attribute to the given entity."""
        self._single_entity = entity

    def create_single_entity_with_config(
        self,
        campaign: models.CircuitExtractionCampaign,  # noqa: ARG002
        db_client: Client,
    ) -> models.CircuitExtractionConfig:
        """Saves the circuit extraction config to the database."""
        L.info(f"2.{self.idx} Saving circuit extraction {self.idx} to database...")

        if not isinstance(self.initialize.circuit, CircuitFromID):
            msg = "Circuit extraction can only be saved to entitycore if circuit is CircuitFromID"
            raise OBIONEError(msg)

        L.info("-- Register CircuitExtractionConfig Entity")
        self._single_entity = db_client.register_entity(
            models.CircuitExtractionConfig(
                name=f"Circuit extraction {self.idx}",
                description=f"Circuit extraction {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                circuit_id=self.initialize.circuit.id_str,
            )
        )

        L.info("-- Upload circuit_extraction_config")
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=models.CircuitExtractionConfig,
            file_path=Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME),
            file_content_type="application/json",
            asset_label="circuit_extraction_config",
        )

        return self._single_entity

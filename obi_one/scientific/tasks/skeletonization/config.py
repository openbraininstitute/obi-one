import abc
import logging
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar

import entitysdk
from entitysdk import models
from entitysdk.types import AssetLabel, ContentType
from pydantic import ConfigDict, Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.library.constants import _COORDINATE_CONFIG_FILENAME, _SCAN_CONFIG_FILENAME

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"


class SkeletonizationScanConfig(ScanConfig, abc.ABC):
    """Abstract base class for skeletonization scan configurations."""

    single_coord_class_name: ClassVar[str] = "SkeletonizationSingleConfig"
    name: ClassVar[str] = "Skeletonization Campaign"
    description: ClassVar[str] = "Skeletonization campaign"

    _campaign: entitysdk.models.SkeletonizationCampaign = None

    model_config = ConfigDict(
        json_schema_extra={
            "ui_enabled": True,
            "group_order": [
                BlockGroup.SETUP_BLOCK_GROUP,
            ],
        }
    )

    class Initialize(Block):
        cell_mesh: EMCellMeshFromID | list[EMCellMeshFromID] = Field(
            title="EM Cell Mesh",
            description="EM cell mesh to use for skeletonization.",
            json_schema_extra={"ui_element": "model_identifier"},
        )

        neuron_voxel_size: (
            Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]
            | list[Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]]
        ) = Field(
            default=0.1,
            title="Neuron Voxel Size",
            description="Neuron reconstruction resolution in micrometers.",
            json_schema_extra={"ui_element": "float_parameter_sweep", "units": "μm"},
        )

        spines_voxel_size: (
            Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]
            | list[Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]]
        ) = Field(
            default=0.1,
            title="Spine Voxel Size",
            description="Spine reconstruction resolution in micrometers.",
            json_schema_extra={"ui_element": "float_parameter_sweep", "units": "μm"},
        )

    info: Info = Field(
        title="Info",
        description="Information about the skeletonization campaign.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP_BLOCK_GROUP,
            "group_order": 0,
        },
    )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the skeletonization.",
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
    ) -> entitysdk.models.SkeletonizationCampaign:
        """Initializes the simulation campaign in the database."""
        L.info("1. Initializing simulation campaign in the database...")

        if multiple_value_parameters_dictionary is None:
            multiple_value_parameters_dictionary = {}

        L.info("-- Register SimulationCampaign Entity")
        if isinstance(
            self.initialize.cell_mesh,
            EMCellMeshFromID,
        ):
            input_meshes = [self.initialize.cell_mesh.entity(db_client)]

        elif isinstance(self.initialize.cell_mesh, list):
            if len(self.initialize.cell_mesh) > 0:
                input_meshes = [mesh.entity(db_client) for mesh in self.initialize.cell_mesh]
            else:
                msg = "No cell meshes provided for skeletonization campaign!"
                raise OBIONEError(msg)

        self._campaign = db_client.register_entity(
            entitysdk.models.SkeletonizationCampaign(
                name=self.info.campaign_name,
                description=self.info.campaign_description,
                input_meshes=input_meshes,
                scan_parameters=multiple_value_parameters_dictionary,
            )
        )

        L.info("-- Upload campaign_generation_config")
        _ = db_client.upload_file(
            entity_id=self._campaign.id,
            entity_type=entitysdk.models.SkeletonizationCampaign,
            file_path=output_root / _SCAN_CONFIG_FILENAME,
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.campaign_generation_config,
        )

        return self._campaign

    def create_campaign_generation_entity(
        self,
        skeletonization_configs: list[entitysdk.models.SkeletonizationConfig],
        db_client: entitysdk.client.Client,
    ) -> None:
        L.info("3. Saving completed simulation campaign generation")

        L.info("-- Register SimulationGeneration Entity")
        db_client.register_entity(
            entitysdk.models.SkeletonizationConfigGeneration(
                start_time=datetime.now(UTC),
                used=[self._campaign],
                generated=skeletonization_configs,
            )
        )


class SkeletonizationSingleConfig(SkeletonizationScanConfig, SingleConfigMixin):
    _single_entity: entitysdk.models.SkeletonizationConfig

    @property
    def single_entity(self) -> entitysdk.models.SkeletonizationConfig:
        return self._single_entity

    def set_single_entity(self, entity: entitysdk.models.SkeletonizationConfig) -> None:
        """Sets the single entity attribute to the given entity."""
        self._single_entity = entity

    def create_single_entity_with_config(
        self, campaign: entitysdk.models.SkeletonizationCampaign, db_client: entitysdk.client.Client
    ) -> entitysdk.models.SkeletonizationConfig:
        """Saves the SkeletonizationConfig to the database."""
        L.info(f"2.{self.idx} Saving SkeletonizationConfig {self.idx} to database...")

        L.info("-- Register SkeletonizationConfig Entity")
        self._single_entity = db_client.register_entity(
            entitysdk.models.SkeletonizationConfig(
                name=f"SkeletonizationConfig {self.idx}",
                description=f"SkeletonizationConfig {self.idx}",
                scan_parameters=self.single_coordinate_scan_params.dictionary_representaiton(),
                skeletonization_campaign_id=campaign.id,
                em_cell_mesh_id=self.initialize.cell_mesh.id_str,
            )
        )

        L.info("-- Upload skeltonization_config asset")
        L.info(Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME))
        L.info(self.single_entity)
        L.info(self.single_entity.id)
        _ = db_client.upload_file(
            entity_id=self.single_entity.id,
            entity_type=models.SkeletonizationConfig,
            file_path=Path(self.coordinate_output_root, _COORDINATE_CONFIG_FILENAME),
            file_content_type=ContentType.application_json,
            asset_label=AssetLabel.skeletonization_config,
        )

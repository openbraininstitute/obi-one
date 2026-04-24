import abc
import logging
from enum import StrEnum
from typing import Annotated, ClassVar

from entitysdk.client import Client
from entitysdk.models import Entity
from entitysdk.types import TaskActivityType, TaskConfigType
from pydantic import ConfigDict, Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.core.units import Units
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"


class SkeletonizationScanConfig(InfoScanConfig, abc.ABC):
    """Abstract base class for skeletonization scan configurations."""

    single_coord_class_name: ClassVar[str] = "SkeletonizationSingleConfig"
    name: ClassVar[str] = "Skeletonization Campaign"
    description: ClassVar[str] = "Skeletonization campaign"

    model_config = ConfigDict(
        json_schema_extra={
            SchemaKey.UI_ENABLED: True,
            SchemaKey.GROUP_ORDER: [
                BlockGroup.SETUP_BLOCK_GROUP,
            ],
        }
    )

    _campaign_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.skeletonization__campaign
    _campaign_generation_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.skeletonization__config_generation
    )

    def input_entities(self, db_client: Client) -> list[Entity]:
        L.info("-- Register SkeletonizationCampaign Entity")
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

        return input_meshes

    class Initialize(Block):
        cell_mesh: EMCellMeshFromID | list[EMCellMeshFromID] = Field(
            title="EM Cell Mesh",
            description="EM cell mesh to use for skeletonization.",
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER},
        )

        neuron_voxel_size: (
            Annotated[PositiveFloat, Field(ge=0.1, le=1.0)]
            | list[Annotated[PositiveFloat, Field(ge=0.005, le=0.1)]]
        ) = Field(
            default=0.1,
            title="Neuron Voxel Size",
            description="Neuron reconstruction resolution in micrometers.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MICROMETERS,
            },
        )

        spines_voxel_size: (
            Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]
            | list[Annotated[PositiveFloat, Field(ge=0.1, le=0.5)]]
        ) = Field(
            default=0.1,
            title="Spine Voxel Size",
            description="Spine reconstruction resolution in micrometers.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.FLOAT_PARAMETER_SWEEP,
                SchemaKey.UNITS: Units.MICROMETERS,
            },
        )

        write_raw_spines: bool = Field(
            default=True,
            title="Include Full Resolution Spines",
            description=(
                "By default a morphology h5 file is created with reconstructed spines. "
                "Set this parameter to True to additionally include the initially "
                "extracted full resolution segmented spine meshes in the h5 file. "
                "This may be useful for use cases which require "
                "the full resolution spine data."
            ),
            json_schema_extra={SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT},
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the skeletonization.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class SkeletonizationSingleConfig(SkeletonizationScanConfig, SingleConfigMixin):
    _single_task_config_type: ClassVar[TaskConfigType] = TaskConfigType.skeletonization__config
    _single_task_activity_type: ClassVar[TaskActivityType] = (
        TaskActivityType.skeletonization__execution
    )

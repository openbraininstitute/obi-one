"""Configuration for building a point neuron circuit from a set of EM cell meshes."""

import logging
from enum import StrEnum
from typing import ClassVar, Self

from entitysdk.client import Client
from entitysdk.models import Entity
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.core.schema import AcceptedInputTypes, SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.named_tuple_from_id import PointNeuronCircuitFromEMInputNamedTuple
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    SETUP_BLOCK_GROUP = "Setup"


class PointNeuronCircuitFromEMScanConfig(InfoScanConfig):
    """Resolve EM connectivity between a set of EM cell meshes for a point neuron circuit."""

    single_coord_class_name: ClassVar[str] = "PointNeuronCircuitFromEMSingleConfig"
    name: ClassVar[str] = "Point neuron circuit from EM"
    description: ClassVar[str] = "Point neuron circuit from EM connectivity campaign"

    def input_entities(self, db_client: Client) -> list[Entity]:
        if isinstance(self.initialize.cell_meshes, PointNeuronCircuitFromEMInputNamedTuple):
            return [m.entity(db_client=db_client) for m in self.initialize.cell_meshes.elements]
        if isinstance(self.initialize.cell_meshes, list):
            # Make sure that there are no duplicates in the returned list of entities.
            to_return = []
            to_return_ids = []
            for input_tuple in self.initialize.cell_meshes:
                for m in input_tuple.elements:
                    if m.id_str not in to_return_ids:
                        to_return_ids.append(m.id_str)
                        to_return.append(m.entity(db_client=db_client))
            return to_return
        msg = (
            "Invalid type for cell_meshes. Expected PointNeuronCircuitFromEMInputNamedTuple "
            "or list of PointNeuronCircuitFromEMInputNamedTuple."
        )
        raise ValueError(msg)

    class Initialize(Block):
        # We use a named tuple instead of a list to group all meshes into a single circuit
        # (so the set is not taken as a scan dimension). Use list[named tuple] to scan over
        # different sets of meshes.
        cell_meshes: (
            PointNeuronCircuitFromEMInputNamedTuple
            | list[PointNeuronCircuitFromEMInputNamedTuple]
        ) = Field(
            title="EM cell meshes",
            description="EM cell meshes to include in the circuit (>= 1).",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER_MULTIPLE,
                SchemaKey.ACCEPTED_INPUT_TYPES: [
                    AcceptedInputTypes.EM_CELL_MESH_FROM_ID,
                ],
            },
        )

        @model_validator(mode="after")
        def check_mesh_structure(self) -> Self:
            if isinstance(self.cell_meshes, list):
                if len(self.cell_meshes) < 1:
                    msg = (
                        "At least one set of EM cell meshes must be provided in "
                        "Point Neuron Circuit From EM Scan Config."
                    )
                    raise OBIONEError(msg)

                tuple_names = [input_tuple.name for input_tuple in self.cell_meshes]
                if len(tuple_names) != len(set(tuple_names)):
                    msg = (
                        "All named tuples in the list of cell_meshes must have unique names "
                        "in Point Neuron Circuit From EM Scan Config."
                    )
                    raise OBIONEError(msg)
            return self

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the point neuron circuit.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )


class PointNeuronCircuitFromEMSingleConfig(PointNeuronCircuitFromEMScanConfig, SingleConfigMixin):
    class Initialize(PointNeuronCircuitFromEMScanConfig.Initialize):
        cell_meshes: "PointNeuronCircuitFromEMInputNamedTuple"

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the point neuron circuit.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

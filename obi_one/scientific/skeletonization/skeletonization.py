import json
import os
from typing import ClassVar, Literal, Self, Annotated

from pydantic import Field, PrivateAttr, model_validator, NonNegativeInt, NonNegativeFloat, PositiveInt, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.info import Info
from obi_one.core.exception import OBIONE_Error

from obi_one.database.circuit_from_id import CircuitFromID

import entitysdk
from collections import OrderedDict

from datetime import UTC, datetime

from pathlib import Path

import logging
L = logging.getLogger(__name__)


class SkelotonizationForm(Form):
    """Skelotonization Form."""

    single_coord_class_name: ClassVar[str] = "Skelotonization"
    name: ClassVar[str] = "Skelotonization Campaign"
    description: ClassVar[str] = "Marwan's awesome skelotonization campaign."

    class Config:
        json_schema_extra = {
            "block_block_group_order": []
        }

    class Initialize(Block):
        mesh_path: Annotated[Path, Field(description="Path to the mesh file to be used for skelotonization.")]

        resolution: Annotated[NonNegativeFloat, Field(
            default=0.01,
            title="Resolution",
            description="Resolution of the skelotonization in micrometers (um).",
            ge=0.001,
            le=1.0,
            units="um"
        )]

        fix_soma_slicing_artifacts: Annotated[bool, Field(
            default=False,
            title="Fix Soma Slicing Artifacts",
            description="Whether to fix artifacts caused by soma slicing during skelotonization."
        )]



        
        


    initialize: Initialize = Field(title="Initialization", description="Parameters for initializing the skelotonization.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=1)
    info: Info = Field(title="Info", description="Information about the simulation campaign.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=0)

   
class Skelotonization(SkelotonizationForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    def generate(self, db_client: entitysdk.client.Client = None):
        """Generates SONATA simulation config .json file."""



        command = ""
        command += str(self.pixels) + str(self.mesh_path)
        

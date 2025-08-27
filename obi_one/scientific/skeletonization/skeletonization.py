import logging
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import entitysdk
from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.info import Info
from obi_one.core.single import SingleCoordinateMixin

L = logging.getLogger(__name__)

from enum import StrEnum


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    SPINES_BLOCK_GROUP = "Spines"
    ADVANCED_BLOCK_GROUP = "Advanced"


class SpineExtractionType(StrEnum):
    no_spines = "No Spine Extraction"
    spine_statistics = "Spine Statistics"
    spine_statistics_and_skeletons = "Spine Statistics & Skeletons"
    spine_statistics_and_meshes = "Spine Statistics & Meshes"
    spine_statistics_skeletons_and_meshes = "Spine Statistics, Skeletons & Meshes"


class SkelotonizationForm(Form):
    """Skelotonization Form."""

    single_coord_class_name: ClassVar[str] = "Skelotonization"
    name: ClassVar[str] = "Skelotonization Campaign"
    description: ClassVar[str] = "Skeletonization Campaign Form"

    class Config:
        json_schema_extra = {"block_block_group_order": []}

    class Initialize(Block):
        mesh_path: Annotated[
            Path, Field(description="Path to the mesh file to be used for skelotonization.")
        ]

        resolution: Annotated[
            PositiveFloat,
            Field(
                default=0.01,
                title="Resolution",
                description="Resolution of the skelotonization in micrometers (um).",
                ge=0.001,
                le=1.0,
                units="um",
            ),
        ]

    class SpineExtraction(Block):
        spine_extraction_type: Annotated[
            SpineExtractionType,
            Field(title="Spine Extraction Type", description="Spine Extraction Type Description"),
        ] = SpineExtractionType.spine_statistics_skeletons_and_meshes

    # class SomaSegmentation(Block):

    #     fix_soma_slicing_artifacts: Annotated[bool, Field(
    #         default=False,
    #         title="Fix Soma Slicing Artifacts",
    #         description="Due to some reconstruction artifacts, so slices can be missing and this impacts mainly the soma. If you enable this option, we fix any slicing artifacts encountered and reconstruct a fixed soma."
    #     )]

    #     segment_soma: Annotated[bool, Field(
    #         default=False,
    #         title="Segment Soma",
    #         description="If this flag is set, the soma will be segmented and a high quality mesh object will be created."
    #     )]

    #     soma_segmentation_radius_threshold: Annotated[PositiveFloat, Field(
    #         default=1.75,
    #         title="Soma Segmentation Radius Threshold",
    #         description="This value is used to accurately segment the soma, by default 2.0 for human neurons, and 1.75 for mouse neurons.",
    #         ge=1.5,
    #         le=2.5,
    #         units="um"
    #     )]

    class AdvancedOptions(Block):
        reconstruction_axis: Annotated[
            Literal["X", "Y", "Z", "XYZ_AND", "XYZ_OR"],
            Field(
                default="X",
                title="Reconstruction Axis",
                description="Axis along which the skelotonization will be reconstructed.",
            ),
        ]

        project_reconstructions: Annotated[
            bool,
            Field(
                default=False,
                title="Project Reconstructions",
                description="For validation. Creates an image.",
            ),
        ]

    info: Info = Field(
        title="Info",
        description="Information about the campaign.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=0,
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the skelotonization.",
        group=BlockGroup.SETUP_BLOCK_GROUP,
        group_order=1,
    )

    spine_extraction: SpineExtraction = Field(
        title="Spine Extraction",
        description="Parameters for spine extraction.",
        group=BlockGroup.SPINES_BLOCK_GROUP,
        group_order=0,
    )

    advanced_options: AdvancedOptions = Field(
        title="Advanced Options",
        description="Advanced parameters",
        group=BlockGroup.ADVANCED_BLOCK_GROUP,
        group_order=0,
    )


class Skelotonization(SkelotonizationForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    def generate(self, db_client: entitysdk.client.Client = None):
        """Generate"""
        print(self.initialize.mesh_path)
        print(self.initialize.resolution)

        print(self.spine_extraction.processing_pipeline)

        print(self.advanced_options.reconstruction_axis)
        print(self.advanced_options.project_reconstructions)

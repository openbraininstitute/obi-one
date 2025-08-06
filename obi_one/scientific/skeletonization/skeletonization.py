import json
import os
from typing import ClassVar, Literal, Self, Annotated

from pydantic import Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.form import Form
from obi_one.core.single import SingleCoordinateMixin
from obi_one.core.info import Info

import entitysdk
from collections import OrderedDict

from pathlib import Path

import logging
L = logging.getLogger(__name__)

from enum import StrEnum
class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"
    ADVANCED_BLOCK_GROUP = "Advanced"

class SkelotonizationForm(Form):
    """Skelotonization Form."""

    single_coord_class_name: ClassVar[str] = "Skelotonization"
    name: ClassVar[str] = "Skelotonization Campaign"
    description: ClassVar[str] = "Skeletonization Campaign Form"

    class Config:
        json_schema_extra = {
            "block_block_group_order": []
        }

    class Initialize(Block):
        mesh_path: Annotated[Path, Field(description="Path to the mesh file to be used for skelotonization.")]

        resolution: Annotated[PositiveFloat, Field(
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
            description="Due to some reconstruction artifacts, so slices can be missing and this impacts mainly the soma. If you enable this option, we fix any slicing artifacts encountered and reconstruct a fixed soma."
        )]

        segment_soma: Annotated[bool, Field(
            default=False,
            title="Segment Soma",
            description="If this flag is set, the soma will be segmented and a high quality mesh object will be created."
        )]

        soma_segmentation_radius_threshold: Annotated[PositiveFloat, Field(
            default=1.75,
            title="Soma Segmentation Radius Threshold",
            description="This value is used to accurately segment the soma, by default 2.0 for human neurons, and 1.75 for mouse neurons.",
            ge=1.5,
            le=2.5,
            units="um"
        )]

        detach_spikes_from_skeleton: Annotated[bool, Field(
            default=False,
            title="Detach Spikes from Skeleton",
            description="Remove the spine branches from the neuronal morphology skeleton, with which the final morphology of the neuron will reflect only the neuronal branches (axons, basal and apical dendrites)."
        )]

        segment_spines: Annotated[bool, Field(
            default=False,
            title="Segment Spines",
            description="Segment the spine geometries from the input mesh."
        )]

        reconstruct_spike_meshes: Annotated[bool, Field(
            default=False,
            title="Reconstruct Spike Meshes",
            description="Reconstruct high quality spine geometries based on the segmented spine geometries."
        )]

        reconstruct_spike_morphologies: Annotated[bool, Field(
            default=False,
            title="Reconstruct Spike Morphologies",
            description="Use the spine meshes and their branches to reconstruct high quality spine morphologies to be used for the analysis."
        )]

    class AdvancedOptions(Block):
        reconstruction_axis: Annotated[Literal["X", "Y", "Z", "XYZ_AND", "XYZ_OR"], Field(
            default="X",
            title="Reconstruction Axis",
            description="Axis along which the skelotonization will be reconstructed."
        )]

        project_reconstructions: Annotated[bool, Field(
            default=False,
            title="Project Reconstructions",
            description="For validation. Creates an image."
        )]

    class OutputOptions(Block):
        export_segmented_soma_mesh: Annotated[bool, Field(
            default=False,
            title="Export Segmented Soma Mesh",
            description="Export the segmented soma mesh."
        )]

        export_segmented_spines: Annotated[bool, Field(
            default=False,
            title="Export Segmented Spine Meshes",
            description="Export the segmented spine meshes."
        )]

        export_spine_morphologies: Annotated[bool, Field(
            default=False,
            title="Export Spine Morphologies",
            description="Export the reconstructed spine morphologies."
        )]

        export_improved_neuron_meshes_with_spines: Annotated[bool, Field(
            default=False,
            title="Export Improved Neuron Meshes (including spines)",
            description="Export a high quality reconstructed mesh from the input mesh (including the spines)."
        )]

        export_improved_neuron_mesh_without_spines: Annotated[bool, Field(
            default=False,
            title="Export Improved Neuron Mesh (excluding spines)",
            description="Export a high quality reconstructed mesh from the input mesh (excluding the spines)."
        )]

    info: Info = Field(title="Info", description="Information about the campaign.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=0)
    initialize: Initialize = Field(title="Initialization", description="Parameters for initializing the skelotonization.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=1)
    output_options: OutputOptions = Field(title="Output Options", description="Parameters for the output of the skelotonization.", group=BlockGroup.SETUP_BLOCK_GROUP, group_order=2)

    advanced_options: Initialize = Field(title="Advanced Options", description="Advanced parameters", group=BlockGroup.ADVANCED_BLOCK_GROUP, group_order=0)
    


    

   
class Skelotonization(SkelotonizationForm, SingleCoordinateMixin):
    """Only allows single values and ensures nested attributes follow the same rule."""

    def generate(self, db_client: entitysdk.client.Client = None):
        """Generates SONATA simulation config .json file."""



        command = ""
        command += str(self.pixels) + str(self.mesh_path)
        

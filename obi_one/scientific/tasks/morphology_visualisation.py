import abc
import logging
from enum import StrEnum
from pathlib import Path
from typing import Annotated, ClassVar, Literal

import entitysdk
from pydantic import ConfigDict, Field, PositiveFloat

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.single import SingleConfigMixin
from obi_one.core.task import Task
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Authentication and authorization errors."""

    SETUP_BLOCK_GROUP = "Setup"


class MorphologyVisualisationScanConfig(ScanConfig, abc.ABC):
    """."""

    single_coord_class_name: ClassVar[str] = "MorphologyVisualisationSingleConfig"
    name: ClassVar[str] = "Morphology Visualisation Campaign"
    description: ClassVar[str] = "Morphology Visualisation campaign"

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
        cell_morphology: CellMorphologyFromID | list[CellMorphologyFromID] = Field(
            title="Morphology",
            description="Morphology to use for visualization.",
            json_schema_extra={"ui_element": "model_identifier"},
        )

        camera_view: Literal["front", "side", "top", "all"] = Field(
            json_schema_extra={
                "ui_element": "string_selection",
            },
            title="Option",
            description="Option description.",
            default="front",
        )

        close_up_dimensions: (
            Annotated[PositiveFloat, Field(ge=10, le=1000)]
            | list[Annotated[PositiveFloat, Field(ge=10, le=1000)]]
        ) = Field(
            default=15,
            title="Close Up Dimensions",
            description="Close up view dimensions (in microns), only when RENDERING_VIEW=close-up.",
            json_schema_extra={"ui_element": "float_parameter_sweep", "units": "μm"},
        )

        resolution_scale_factor: Annotated[PositiveFloat, Field(ge=1.0, le=10.0)] = Field(
            default=1.0,
            title="Resolution Scale Factor",
            description="Resolution scale factor for rendering, only when RENDER_TO_SCALE=yes.",
            json_schema_extra={"ui_element": "float_parameter_sweep"},
        )

        render_scale_bar: bool = Field(
            default=False,
            title="Render Scale Bar",
            description="Whether to render a scale bar in the visualization.",
            json_schema_extra={"ui_element": "boolean_input"},
        )

        frame_resolution: Annotated[int, Field(ge=512, le=10000)] | list[Annotated[int, Field(ge=512, le=10000)]] = Field(
            default=3000,
            title="Frame Resolution",
            description="Frame resolution (only used if RENDER_IMAGES_TO_SCALE is set to no).",
            json_schema_extra={"ui_element": "int_parameter_sweep", "units": "pixels"},
        )

        render_images_to_scale: bool = Field(
            default=False,
            title="Render Images to Scale",
            description="Renders the frames to scale that is a factor of the largest dimension of the morphology. You can set the scale factor in the resolution scale factor parameter.",
            json_schema_extra={"ui_element": "boolean_input"},
        )

        rendering_view: Literal["wide-shot", "mid-shot", "close-up"] = Field(
            default="full",
            title="Rendering View",
            description="The rendering view defines the extent of the image w.r.t the morphology ",
            json_schema_extra={"ui_element": "string_selection_enhanced",
                               "description_by_key": {
                                    "wide-shot": "Wide shot view of the entire morphology.",
                                    "mid-shot": "Mid shot view showing the reconstructed components only.",
                                    "close-up": "Close-up around the soma with a given dimensions.",
                               },
                                "title_by_key": {
                                    "wide-shot": "Wide Shot",
                                    "mid-shot": "Mid Shot",
                                    "close-up": "Close-Up",
                                },
                            },
            )
        
        shader_type: Literal["default", "transparent", "flat", "toon", "electron-light", "electron-dark", "super-electron-light", "super-electron-dark", "glossy", "glossy-bumpy"] = Field(
            default="default",
            title="Shader Type",
            description="Shader type to use for rendering the morphology.",
            json_schema_extra={"ui_element": "string_selection_enhanced",
                               "description_by_key": {
                                    "default": "Default Lambert-ward shader.",
                                    "transparent": "Transparent shader.",
                                    "flat": "Flat (like matplotlib).",
                                    "toon": "Cartoon shader.",
                                    "electron-light": "Electron microscopy like shader.",
                                    "electron-dark": "Inverted electron microscopy like shader.",
                                    "super-electron-light": "Super electron microscopy like shader.",
                                    "super-electron-dark": "Inverted super electron microscopy like shader.",
                                    "glossy": "Glossy shader like plastic.",
                                    "glossy-bumpy": "Glossy with some bumps on the surface.",
                               },
                                "title_by_key": {
                                    "default": "Default (Lambert-ward)",
                                    "transparent": "Transparent",
                                    "flat": "Flat",
                                    "toon": "Cartoon",
                                    "electron-light": "Electron Light",
                                    "electron-dark": "Electron Dark",
                                    "super-electron-light": "Super Electron Light",
                                    "super-electron-dark": "Super Electron Dark",
                                    "glossy": "Glossy",
                                    "glossy-bumpy": "Glossy Bumpy",
                                },
                            },
            )
        
        soma_color: tuple[float, float, float] = Field(
            default=(1.0, 0.0, 0.0),
            title="Soma Color",
            description="Color of the soma in RGB format (values between 0 and 1).",
            json_schema_extra={"ui_hidden": True},
        )

        axon_color: tuple[float, float, float] = Field(
            default=(0.0, 1.0, 0.0),
            title="Axon Color",
            description="Color of the axon in RGB format (values between 0 and 1).",
            json_schema_extra={"ui_hidden": True},
        )

        basal_dendrites_color: tuple[float, float, float] = Field(
            default=(0.0, 0.0, 1.0),
            title="Basal Dendrites Color",
            description="Color of the basal dendrites in RGB format (values between 0 and 1).",
            json_schema_extra={"ui_hidden": True},
        )

        apical_dendrites_color: tuple[float, float, float] = Field(
            default=(1.0, 1.0, 0.0),
            title="Apical Dendrites Color",
            description="Color of the apical dendrites in RGB format (values between 0 and 1).",
            json_schema_extra={"ui_hidden": True},
        )

        spines_color: tuple[float, float, float] = Field(
            default=(1.0, 0.0, 1.0),
            title="Spines Color",
            description="Color of the spines in RGB format (values between 0 and 1).",
            json_schema_extra={"ui_hidden": True},
        )

        nucleus_color: tuple[float, float, float] = Field(
            default=(0.0, 1.0, 1.0),
            title="Nucleus Color",
            description="Color of the nucleus in RGB format (values between 0 and 1).",
            json_schema_extra={"ui_hidden": True},
        )

        articulations_color: tuple[float, float, float] = Field(
            default=(0.5, 0.5, 0.5),
            title="Articulations Color",
            description="Color of the articulations in RGB format (values between 0 and 1). Applied only if MORPHOLOGY_RECONSTRUCTION_ALGORITHM=articulated-sections",
            json_schema_extra={"ui_hidden": True},
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
    ) -> None:
        """Initializes the simulation campaign in the database."""
        
        return self._campaign

    def create_campaign_generation_entity(
        self,
        skeletonization_configs: list[entitysdk.models.SkeletonizationConfig],
        db_client: entitysdk.client.Client,
    ) -> None:
        pass


class MorphologyVisualisationSingleConfig(SkeletonizationScanConfig, SingleConfigMixin):
    _single_entity: entitysdk.models.SkeletonizationConfig

    @property
    def single_entity(self) -> entitysdk.models.SkeletonizationConfig:
        return self._single_entity

    def set_single_entity(self, entity: entitysdk.models.SkeletonizationConfig) -> None:
        """Sets the single entity attribute to the given entity."""
        self._single_entity = entity

    def create_single_entity_with_config(
        self, campaign: entitysdk.models.SkeletonizationCampaign, db_client: entitysdk.client.Client
    ) -> None:
        pass

def neuro_morph_vis_rgb_representation(color: tuple[float, float, float]) -> str:
    """Converts a tuple of floats representing RGB values to a string representation used in NeuroMorphoVis configuration."""
    return "_".join(str(int(x * 255)) for x in color)

class MorphologyVisualisationTask(Task):
    config: MorphologyVisualisationSingleConfig

    def execute(
        self,
        *,
        db_client: entitysdk.client.Client = None,
        entity_cache: bool = False,  # noqa: ARG002
    ) -> None:
        
        ex_str = ""
        ex_str += "MORPHOLOGY_FILE=" + self.config.initialize.cell_morphology.SWC_PATH + "\n"

        ex_str += "SOMA_COLOR=" + neuro_morph_vis_rgb_representation(self.config.initialize.soma_color) + "\n"
        ex_str += "AXON_COLOR=" + neuro_morph_vis_rgb_representation(self.config.initialize.axon_color) + "\n"
        ex_str += "BASAL_DENDRITES_COLOR=" + neuro_morph_vis_rgb_representation(self.config.initialize.basal_dendrites_color) + "\n"
        ex_str += "APICAL_DENDRITE_COLOR=" + neuro_morph_vis_rgb_representation(self.config.initialize.apical_dendrites_color) + "\n"
        ex_str += "SPINES_COLOR=" + neuro_morph_vis_rgb_representation(self.config.initialize.spines_color) + "\n"
        ex_str += "NUCLEUS_COLOR=" + neuro_morph_vis_rgb_representation(self.config.initialize.nucleus_color) + "\n"

        exc_str += "SHADER=" + self.config.initialize.shader_type + "\n"
        exc_str += "RENDER_SCALE_BAR=" + ("yes" if self.config.initialize.render_scale_bar else "no") + "\n"
        exc_str += "FRAME_RESOLUTION=" + str(self.config.initialize.frame_resolution) + "\n"
        exc_str += "RENDER_IMAGES_TO_SCALE=" + ("yes" if self.config.initialize.render_images_to_scale else "no") + "\n"
        exc_str += "RENDERING_VIEW=" + self.config.initialize.rendering_view + "\n"
        exc_str += "CAMERA_VIEW=" + self.config.initialize.camera_view + "\n"


        # If morphology reconstruction algorithm is set to articulated-sections
        ex_str += "ARTICULATIONS_COLOR=" + neuro_morph_vis_rgb_representation(self.config.initialize.articulations_color) + "\n"

        # if RENDER_TO_SCALE=yes
        ex_str += "RESOLUTION_SCALE_FACTOR=" + str(self.config.initialize.resolution_scale_factor) + "\n"

        # if RENDERING_VIEW=close-up
        ex_str += "CLOSEUP_VIEW_DIMENSIONS=" + str(self.config.initialize.close_up_dimensions) + "\n"


        # ex_str += OUTPUT_DIRECTORY + "\n"

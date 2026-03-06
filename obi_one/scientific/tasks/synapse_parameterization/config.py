import logging
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"


class SynapseParameterizationSingleConfig(OBIBaseModel, SingleConfigMixin):
    name: ClassVar[str] = "Synapse parameterization"
    description: ClassVar[str] = (
        "Generates a physiological parameterization of an anatomical synaptome or replaces an"
        " existing paramterization."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        "ui_enabled": True,
        "group_order": [BlockGroup.SETUP],
    }

    class Initialize(Block):
        synaptome: MEModelWithSynapsesCircuitFromID = Field(
            title="Synaptome",
            description="Synaptome (i.e., circuit of scale single) to (re-)parameterize.",
        )
        pathway_property: str = Field(
            title="Pathway property",
            description="Neuron property (e.g., 'synapse_class') by which to group neurons into"
            " pathways between source and target neuron populations.",
        )
        pathway_param_dict: dict = Field(
            title="Pathway parameters",
            description="Synapse physiology distribution parameters for all pathways in the"
            " ConnPropsModel format of Connectome-Manipulator.",
        )  # TODO: This may be replaced by dedicated entities
        random_seed: int = Field(
            default=1,
            title="Random seed",
            description="Seed for drawing random values from physiological parameter"
            " distributions.",
        )
        overwrite_if_exists: bool = Field(
            title="Overwrite",
            description="Overwrite if a parameterization exists already.",
            default=False,
        )

    info: Info = Field(
        title="Info",
        description="Information about the circuit extraction campaign.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the circuit extraction campaign.",
        json_schema_extra={
            "ui_element": "block_single",
            "group": BlockGroup.SETUP,
            "group_order": 1,
        },
    )

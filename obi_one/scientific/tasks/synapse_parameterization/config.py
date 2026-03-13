import logging
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.blocks.synaptic_parameterization.synaptic_parameterization import (
    OriginalSynapseParameterization,
)
from obi_one.scientific.from_id.circuit_from_id import MEModelWithSynapsesCircuitFromID
from obi_one.scientific.unions.unions_distributions import (
    SynapticParameterizationDistributionReference,
    SynapticParameterizationDistributionUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    NeuronSetUnion,
)
from obi_one.scientific.unions.unions_synaptic_parameterizations import (
    SynapticParameterizationReference,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    SYNAPSE_PARAMETERS = "Synapse parameters"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit components"


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

    synapse_parameterizations: dict[str, OriginalSynapseParameterization] = Field(
        default_factory=dict,
        description="Parameterizations...",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": SynapticParameterizationReference.__name__,
            "singular_name": "Synaptic Parameterization",
            "group": BlockGroup.SYNAPSE_PARAMETERS,
            "group_order": 0,
        },
    )

    distributions: dict[str, SynapticParameterizationDistributionUnion] = Field(
        default_factory=dict,
        description="Distributions for synapse parameterization.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": SynapticParameterizationDistributionReference.__name__,
            "singular_name": "Synaptic Parameterization Distribution",
            "group": BlockGroup.SYNAPSE_PARAMETERS,
            "group_order": 1,
        },
    )

    neuron_sets: dict[str, NeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "reference_type": NeuronSetReference.__name__,
            "singular_name": "Neuron Set",
            "group": BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            "group_order": 0,
        },
    )

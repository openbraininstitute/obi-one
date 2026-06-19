import logging
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    SynapseParameterizationNeuronSetUnion,
)
from obi_one.scientific.unions.unions_synaptic_model_assigner import (
    SynapticModelAssignerReference,
    SynapticModelAssignerUnion,
)
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    SYNAPSE_PARAMETERS = "Synapse parameters"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit components"


class SynapseParameterizationScanConfig(ScanConfig):
    """Generate or replace a physiological parameterization of an anatomical circuit."""

    name: ClassVar[str] = "Synapse parameterization"
    description: ClassVar[str] = (
        "Generates a physiological parameterization of an anatomical circuit or replaces an"
        " existing parameterization."
    )
    single_coord_class_name: ClassVar[str] = "SynapseParameterizationSingleConfig"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.SYNAPSE_PARAMETERS,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
        ],
    }

    class Initialize(Block):
        circuit: CircuitFromID = Field(
            title="Circuit",
            description="Circuit to (re-)parameterize.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
            },
        )

    info: Info = Field(
        title="Info",
        description="Information about the circuit extraction campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the circuit extraction campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    synapse_model_assigners: dict[str, SynapticModelAssignerUnion] = Field(
        default_factory=dict,
        description="Parameterizations...",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticModelAssignerReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Parameterization",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    synaptic_models: dict[str, SynapticModelUnion] = Field(
        default_factory=dict,
        description="Synaptic models for synapse parameterization.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticModelReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Model",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    distributions: dict[str, AllDistributionsUnion] = Field(
        default_factory=dict,
        description="Distributions for synapse parameterization.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Parameterization Distribution",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
            SchemaKey.GROUP_ORDER: 2,
        },
    )

    neuron_sets: dict[str, SynapseParameterizationNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [NeuronSetReference.__name__],
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class SynapseParameterizationSingleConfig(SynapseParameterizationScanConfig, SingleConfigMixin):
    pass

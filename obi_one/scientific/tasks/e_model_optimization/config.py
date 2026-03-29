import logging
from enum import StrEnum
from typing import ClassVar

from obi_one.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.unions.unions_distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions.unions_synaptic_model_assigner import (
    SynapticModelAssignerReference,
    SynapticModelAssignerUnion,
)
from obi_one.scientific.unions.unions_synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)
from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    NeuronSetUnion,
)

L = logging.getLogger(__name__)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    SYNAPSE_PARAMETERS = "Synapse parameters"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit components"


class EModelOptimizationScanConfig(InfoScanConfig, SingleConfigMixin):
    name: ClassVar[str] = "E-Model Optimization"
    description: ClassVar[str] = "Fill description"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP],
    }

    class Initialize(Block):
        morphology: CellMorphologyFromIDFromID = Field(
            title="Morphology",
            description="Morphology description.",
        )

    initialize: Initialize = Field(
        title="Initialization",
        description="Parameters for initializing the campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    # synapse_model_assigners: dict[str, SynapticModelAssignerUnion] = Field(
    #     default_factory=dict,
    #     description="Parameterizations...",
    #     json_schema_extra={
    #         SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
    #         SchemaKey.REFERENCE_TYPE: SynapticModelAssignerReference.__name__,
    #         SchemaKey.SINGULAR_NAME: "Synaptic Parameterization",
    #         SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
    #         SchemaKey.GROUP_ORDER: 0,
    #     },
    # )

    # synaptic_models: dict[str, SynapticModelUnion] = Field(
    #     default_factory=dict,
    #     description="Synaptic models for synapse parameterization.",
    #     json_schema_extra={
    #         SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
    #         SchemaKey.REFERENCE_TYPE: SynapticModelReference.__name__,
    #         SchemaKey.SINGULAR_NAME: "Synaptic Model",
    #         SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
    #         SchemaKey.GROUP_ORDER: 1,
    #     },
    # )

    # distributions: dict[str, AllDistributionsUnion] = Field(
    #     default_factory=dict,
    #     description="Distributions for synapse parameterization.",
    #     json_schema_extra={
    #         SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
    #         SchemaKey.REFERENCE_TYPE: AllDistributionsReference.__name__,
    #         SchemaKey.SINGULAR_NAME: "Synaptic Parameterization Distribution",
    #         SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
    #         SchemaKey.GROUP_ORDER: 2,
    #     },
    # )

    # neuron_sets: dict[str, NeuronSetUnion] = Field(
    #     default_factory=dict,
    #     description="Neuron sets for the simulation.",
    #     json_schema_extra={
    #         SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
    #         SchemaKey.REFERENCE_TYPE: NeuronSetReference.__name__,
    #         SchemaKey.SINGULAR_NAME: "Neuron Set",
    #         SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
    #         SchemaKey.GROUP_ORDER: 0,
    #     },
    # )


class EModelOptimizationSingleConfig(EModelOptimizationScanConfig, SingleConfigMixin):
    pass

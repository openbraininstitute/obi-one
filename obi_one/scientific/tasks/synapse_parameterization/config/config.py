"""The synapse parameterization scan configuration."""

import logging
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.fill_none_references import BlockDefault
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
    AllVirtualNeurons,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    InhibitoryTsodyksMarkramSynapticModel,
)
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    NEURONSynapseParameterizationNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
    VirtualNeuronSetReference,
)
from obi_one.scientific.unions_and_references.reference_tags import ReferenceTag
from obi_one.scientific.unions_and_references.synaptic_model_assigner import (
    SynapticModelAssignerReference,
    SynapticModelAssignerUnion,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)

L = logging.getLogger(__name__)


DEFAULT_SYNAPTIC_MODEL_NAME = "Default: Excitatory Tsodyks-Markram"

# One entry per role a reference field can play in this config: the reference type to build
# (which has to match the field's own union), the dictionary the block is registered in, the
# name it takes there, and a factory for the block itself. Both the schema the UI reads and the
# references the fill pass substitutes are derived from this, so they cannot disagree.
_DEFAULTS: dict[str, BlockDefault] = {
    ReferenceTag.SYNAPTIC_MODEL: BlockDefault(
        SynapticModelReference,
        "synaptic_models",
        DEFAULT_SYNAPTIC_MODEL_NAME,
        ExcitatoryTsodyksMarkramSynapticModel,
    ),
    # "No restriction" for the assigner roles: an inter- or presynaptic assigner naming neither
    # end then behaves like the all-pairs one, which is what placing no restriction means.
    # Biophysical because that is what a chemical edge population connects in the normal case,
    # and because there is no atomic non-virtual reference type to carry a broader default. An
    # edge population on point or virtual neurons has to name its ends, and the assigner's own
    # validation says which one does not fit.
    ReferenceTag.SYNAPSE_ASSIGNMENT_SOURCE: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.SYNAPSE_ASSIGNMENT_TARGET: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    # Every neuron of the combined set's own type. One entry per type because each combined
    # subclass redeclares its operands with its own reference union.
    ReferenceTag.ANY_NEURON_SET_OPERAND: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.NON_VIRTUAL_NEURON_SET_OPERAND: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.BIOPHYSICAL_NEURON_SET_OPERAND: BlockDefault(
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.POINT_NEURON_SET_OPERAND: BlockDefault(
        PointNeuronSetReference,
        "neuron_sets",
        "Default: All Point Neurons",
        AllPointNeurons,
    ),
    ReferenceTag.VIRTUAL_NEURON_SET_OPERAND: BlockDefault(
        VirtualNeuronSetReference,
        "neuron_sets",
        "Default: All Virtual Neurons",
        AllVirtualNeurons,
    ),
}


def _distribution_defaults() -> dict[str, BlockDefault]:
    """The parameters of every concrete Tsodyks-Markram model, keyed by the role each plays.

    Both models, because excitatory and inhibitory synapses take different values for the same
    parameter and so answer different roles - eighteen between them, not nine shared.
    """
    return {
        tag: BlockDefault(
            AllDistributionsReference, "distributions", name, lambda d=distribution: d
        )
        for model in (
            ExcitatoryTsodyksMarkramSynapticModel,
            InhibitoryTsodyksMarkramSynapticModel,
        )
        for tag, (name, distribution) in model.default_distributions_by_role().items()
    }


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    SYNAPSE_PARAMETERS = "Synapse parameters"
    CIRCUIT_COMPONENTS_BLOCK_GROUP = "Circuit components"


class SynapseParameterizationScanConfig(InfoScanConfig):
    """Generate or replace a physiological parameterization of an anatomical circuit."""

    name: ClassVar[str] = "Synapse parameterization"
    description: ClassVar[str] = (
        "Generates a physiological parameterization of an anatomical circuit or replaces an"
        " existing parameterization."
    )

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.SYNAPSE_PARAMETERS,
            BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
        ],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

    @staticmethod
    def default_blocks() -> dict[str, BlockDefault]:
        """What each unset reference resolves to, keyed by the role the field plays.

        The only thing this config says about its defaults: the base resolves them into
        references and publishes them to the schema.
        """
        return {**_distribution_defaults(), **_DEFAULTS}

    class Initialize(Block):
        circuit: CircuitFromID = Field(
            title="Circuit",
            description="Circuit to (re-)parameterize.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
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

    distributions: dict[str, AllDistributionsUnion] = Field(
        default_factory=dict,
        description="Distributions for synapse parameterization.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [AllDistributionsReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Parameterization Distribution",
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

    synapse_model_assigners: dict[str, SynapticModelAssignerUnion] = Field(
        default_factory=dict,
        description="Parameterizations...",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: [SynapticModelAssignerReference.__name__],
            SchemaKey.SINGULAR_NAME: "Synaptic Parameterization",
            SchemaKey.GROUP: BlockGroup.SYNAPSE_PARAMETERS,
            SchemaKey.GROUP_ORDER: 2,
        },
    )

    neuron_sets: dict[str, NEURONSynapseParameterizationNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS_BLOCK_GROUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class SynapseParameterizationSingleConfig(SynapseParameterizationScanConfig, SingleConfigMixin):
    """Single-coordinate synapse parameterization configuration."""

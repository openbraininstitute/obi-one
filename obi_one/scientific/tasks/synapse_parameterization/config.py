import logging
from collections.abc import Callable
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
    AllVirtualNeurons,
)
from obi_one.scientific.blocks.synaptic_models.tsodyks_markram import (
    ExcitatoryTsodyksMarkramSynapticModel,
    tsodyks_markram_default_distributions,
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
_DEFAULTS: dict[str, tuple[type, str, str, Callable[[], Block]]] = {
    ReferenceTag.SYNAPTIC_MODEL: (
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
    ReferenceTag.SYNAPSE_ASSIGNMENT_SOURCE: (
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.SYNAPSE_ASSIGNMENT_TARGET: (
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    # Every neuron of the combined set's own type. One entry per type because each combined
    # subclass redeclares its operands with its own reference union.
    ReferenceTag.ANY_NEURON_SET_OPERAND: (
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.NON_VIRTUAL_NEURON_SET_OPERAND: (
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.BIOPHYSICAL_NEURON_SET_OPERAND: (
        BiophysicalNeuronSetReference,
        "neuron_sets",
        "Default: All Biophysical Neurons",
        AllBiophysicalNeurons,
    ),
    ReferenceTag.POINT_NEURON_SET_OPERAND: (
        PointNeuronSetReference,
        "neuron_sets",
        "Default: All Point Neurons",
        AllPointNeurons,
    ),
    ReferenceTag.VIRTUAL_NEURON_SET_OPERAND: (
        VirtualNeuronSetReference,
        "neuron_sets",
        "Default: All Virtual Neurons",
        AllVirtualNeurons,
    ),
}


def _distribution_defaults() -> dict[str, tuple[type, str, str, Callable[[], Block]]]:
    """The nine Tsodyks-Markram parameters, in the same shape as `_DEFAULTS`."""
    return {
        tag: (AllDistributionsReference, "distributions", name, lambda d=distribution: d)
        for tag, (name, distribution) in tsodyks_markram_default_distributions().items()
    }


def _all_defaults() -> dict[str, tuple[type, str, str, Callable[[], Block]]]:
    return {**_distribution_defaults(), **_DEFAULTS}


def _reference_tag_defaults() -> dict[str, dict]:
    """What the UI reads: the name each role resolves to, and the block behind that name."""
    return {
        tag: {"name": name, "block": factory().model_dump(mode="json")}
        for tag, (_reference_type, _dict_name, name, factory) in _all_defaults().items()
    }


def _resolved(
    reference_type: type, block_dict_name: str, name: str, block: Block
) -> BlockReference:
    """A reference to a block the config supplies rather than the user.

    The block carries the name too, or it serializes without one once it is registered under
    that key.
    """
    reference = reference_type(block_dict_name=block_dict_name, block_name=name)
    block.set_block_name(name)
    reference.block = block
    return reference


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
        # The UI renders a `reference` field only for a reference type named here, so a type
        # left out hides every field that points at it - not just its dropdown's options.
        # Keyed off ALL_NEURON_SETS_REFERENCE_TYPES rather than spelled out, so the neuron set
        # entries cannot drift from the union the `neuron_sets` field below accepts.
        #
        # These read as prompts rather than defaults because, for the fields they cover, there
        # is no default: an assigner without a synaptic model or a neuron set cannot run, and
        # says so. The fields that do have a default are tagged instead, below.
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            AllDistributionsReference.__name__: "Default",
            SynapticModelReference.__name__: "Select a synaptic model",
            **dict.fromkeys(ALL_NEURON_SETS_REFERENCE_TYPES, "Select a neuron set"),
        },
        # Keyed by the role a field plays rather than by its reference type, which is the only
        # way to give the nine Tsodyks-Markram parameters nine different answers - they all
        # accept AllDistributionsReference, so the map above can offer them only one.
        SchemaKey.REFERENCE_TAG_DEFAULTS: _reference_tag_defaults(),
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

    @staticmethod
    def default_block_references() -> dict[str, BlockReference]:
        """The block reference each unset field resolves to, keyed by the role it plays.

        Consumed by `fill_none_references_in_config`. Each reference carries its block, so the
        caller can register the ones actually used and leave the rest uncreated - a config whose
        fields are all named explicitly gains no blocks it never refers to.
        """
        return {
            tag: _resolved(reference_type, dict_name, name, factory())
            for tag, (reference_type, dict_name, name, factory) in _all_defaults().items()
        }

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

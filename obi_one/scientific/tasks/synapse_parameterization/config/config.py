"""The synapse parameterization scan configuration."""

import logging
from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.block_reference import BlockReference
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.entity_property_types import (
    MappedPropertiesGroup,
)
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.tasks.synapse_parameterization.config.default import (
    _all_defaults,
    _reference_tag_defaults,
    _resolved,
)
from obi_one.scientific.unions_and_references.combined_neuron_sets import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    NEURONSynapseParameterizationNeuronSetUnion,
)
from obi_one.scientific.unions_and_references.distributions import (
    AllDistributionsReference,
    AllDistributionsUnion,
)
from obi_one.scientific.unions_and_references.synaptic_model_assigner import (
    SynapticModelAssignerReference,
    SynapticModelAssignerUnion,
)
from obi_one.scientific.unions_and_references.synaptic_models import (
    SynapticModelReference,
    SynapticModelUnion,
)

L = logging.getLogger(__name__)


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

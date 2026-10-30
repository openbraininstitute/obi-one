"""Scan and single-config classes for circuit simplification."""

from enum import StrEnum
from typing import ClassVar, Self

from entitysdk import Client, models
from pydantic import Field, model_validator

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.core.single import SingleConfigMixin
from obi_one.scientific.blocks.neuron_sets.specific import AllBiophysicalNeurons
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.entity_property_types import MappedPropertiesGroup
from obi_one.scientific.library.info_scan_config.config import InfoScanConfig
from obi_one.scientific.tasks.circuit_simplification.algorithms.metadata import (
    algorithm_supports_node_selection,
)
from obi_one.scientific.tasks.circuit_simplification.algorithms.models import (
    SimplificationAlgorithmUnion,
    default_simplification_algorithms,
)
from obi_one.scientific.tasks.circuit_simplification.references import (
    SIMPLIFICATION_ALGORITHM_REFERENCE_TYPES,
)
from obi_one.scientific.tasks.generate_simulations.config.neuron.neuron_circuit import (
    CircuitDiscriminator,
)
from obi_one.scientific.unions_and_references.neuron_sets import (
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
    ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION,
    AtomicBiophysicalNeuronSetUnion,
    BiophysicalNeuronSetReference,
)


class BlockGroup(StrEnum):
    """Block groups for the simplification form."""

    SETUP = "Setup"
    CIRCUIT_COMPONENTS = "Circuit components"
    SIMPLIFICATION = "Simplification"


class CircuitSimplificationScanConfig(InfoScanConfig):
    """ScanConfig for simplifying SONATA circuits.

    Transforms detailed biophysical circuits into simplified representations
    while preserving network connectivity. Multiple target models can be selected,
    each producing a separate simplified output circuit.
    """

    name: ClassVar[str] = "Circuit Simplification"
    description: ClassVar[str] = (
        "Simplifies a SONATA circuit by reducing biophysical complexity while preserving"
        " network connectivity. Supports multiple target models (single-compartment,"
        " LIF, AdEx, Izhikevich, GLIF, GIF, Neuron_Reduce, NEAT). Point-neuron models are"
        " exported to NEST (or Brian2 for AdEx); single-compartment, Neuron_Reduce and"
        " NEAT produce NEURON circuits."
    )

    default_target_neuron_set_name: ClassVar[str] = "Default: All Biophysical Neurons"
    default_neuron_set_type: ClassVar[type[AllBiophysicalNeurons]] = AllBiophysicalNeurons

    @property
    def default_neuron_set_reference(self) -> BiophysicalNeuronSetReference:
        """The default neuron set reference (all biophysical neurons)."""
        ref = BiophysicalNeuronSetReference(
            block_dict_name="neuron_sets", block_name=self.default_target_neuron_set_name
        )
        ref.block = self.default_neuron_set_type()
        ref.block.set_block_name(self.default_target_neuron_set_name)
        return ref

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [
            BlockGroup.SETUP,
            BlockGroup.CIRCUIT_COMPONENTS,
            BlockGroup.SIMPLIFICATION,
        ],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
        SchemaKey.DEFAULT_BLOCK_REFERENCE_LABELS: {
            BiophysicalNeuronSetReference.__name__: default_target_neuron_set_name,
        },
    }

    @model_validator(mode="after")
    def check_neuron_set_supported(self) -> Self:
        """A target neuron set is only accepted when every selected algorithm supports it."""
        if self.initialize.target_neuron_set is None:
            return self
        unsupported = sorted(
            block.algorithm_name
            for block in self.algorithms.values()
            if not algorithm_supports_node_selection(block.algorithm_name)
        )
        if unsupported:
            msg = (
                "A target neuron set is only supported by algorithms that allow partial"
                f" simplification; not supported by: {', '.join(unsupported)}."
                " Remove the target neuron set to simplify all biophysical neurons."
            )
            raise ValueError(msg)
        return self

    def input_entities(self, db_client: Client) -> list[models.Entity]:
        input_entities = []
        if isinstance(self.initialize.circuit, CircuitFromID):
            input_entities.extend([self.initialize.circuit.entity(db_client=db_client)])
        elif isinstance(self.initialize.circuit, list):
            for circuit in self.initialize.circuit:
                if isinstance(circuit, CircuitFromID):
                    input_entities.extend([circuit.entity(db_client=db_client)])
        return input_entities

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Input SONATA circuit to be simplified.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 100,
            },
        )
        target_neuron_set: ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_UNION | None = Field(  # ty:ignore[no-matching-overload]
            default=None,
            title="Target neuron set",
            description=(
                "Neuron set to simplify (e.g. by e-type or m-type). If empty, all biophysical"
                " neurons are simplified. Only supported by the single-compartment algorithm."
            ),
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.REFERENCE,
                SchemaKey.REFERENCE_TYPES: ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
                SchemaKey.PARAMETER_ORDER_PRIORITY: 99,
            },
        )

    algorithms: dict[str, SimplificationAlgorithmUnion] = Field(  # ty:ignore[no-matching-overload]
        default_factory=default_simplification_algorithms,
        title="Algorithms",
        description=(
            "Add one or more target models for simplification."
            " Each selected model produces a separate simplified output circuit."
        ),
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Algorithm",
            SchemaKey.REFERENCE_TYPES: SIMPLIFICATION_ALGORITHM_REFERENCE_TYPES,
            SchemaKey.GROUP: BlockGroup.SIMPLIFICATION,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    info: Info = Field(
        title="Info",
        description="Information about the simplification campaign.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 0,
        },
    )
    initialize: Initialize = Field(
        title="Initialization",
        description="Input circuit to be simplified.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.SETUP,
            SchemaKey.GROUP_ORDER: 1,
        },
    )
    neuron_sets: dict[str, AtomicBiophysicalNeuronSetUnion] = Field(  # ty:ignore[no-matching-overload]
        default_factory=dict,
        title="Neuron sets",
        description="Neuron sets that can be selected as the target of the simplification.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.REFERENCE_TYPES: ATOMIC_BIOPHYSICAL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.GROUP: BlockGroup.CIRCUIT_COMPONENTS,
            SchemaKey.GROUP_ORDER: 0,
        },
    )


class CircuitSimplificationSingleConfig(CircuitSimplificationScanConfig, SingleConfigMixin):
    """Single-coordinate configuration for circuit simplification.

    Enforces that all parameters are single values (no scan dimensions).
    """

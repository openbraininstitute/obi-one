from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.core.schema import SchemaKey, UIElement
from obi_one.scientific.library.entity_property_types import (
    CircuitUsability,
    MappedPropertiesGroup,
)
from obi_one.scientific.tasks.generate_simulations.config.circuit import (
    CircuitDiscriminator,
)
from obi_one.scientific.unions.unions_neuron_sets_2 import (
    ALL_NEURON_SETS_REFERENCE_TYPES,
    AllNeuronSetUnion,
)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    EXTRACTION_TARGET = "Extraction Target"


class EntityDependentBlockExample(Block):
    """Entity Dependent Block Example Description."""

    title: ClassVar[str] = "Entity Dependent Block Example Title"

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.BLOCK_USABILITY_DICTIONARY: {
            SchemaKey.PROPERTY_GROUP: MappedPropertiesGroup.CIRCUIT,
            SchemaKey.PROPERTY: CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI,
            SchemaKey.FALSE_MESSAGE: "This example block is not available for this circuit.",
        },
    }


class SchemaExampleScanConfig(ScanConfig):
    """ScanConfig for extracting sub-circuits from larger circuits."""

    single_coord_class_name: ClassVar[str] = ""
    name: ClassVar[str] = "Schema Example"
    description: ClassVar[str] = "Useful for testing and generating example schema."

    json_schema_extra_additions: ClassVar[dict] = {
        SchemaKey.UI_ENABLED: True,
        SchemaKey.GROUP_ORDER: [BlockGroup.SETUP, BlockGroup.EXTRACTION_TARGET],
        SchemaKey.PROPERTY_ENDPOINTS: {
            MappedPropertiesGroup.CIRCUIT: "/mapped-circuit-properties/{circuit_id}",
        },
    }

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.MODEL_IDENTIFIER,
            },
        )
        example_boolean_input: bool = Field(
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.BOOLEAN_INPUT,
            },
            default=True,
            title="Include Virtual Populations",
            description="Include virtual neurons which target the cells contained in the specified"
            " neuron set (together with their connectivity onto the specified neuron set) in the"
            " extracted sub-circuit.",
        )

        temp_option_remove_string_selection: Literal["A", "B", "C"] = Field(
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION,
            },
            title="Option",
            description="Option description.",
            default="A",
        )

        temp_option_remove_string_constant: Literal["A"] = Field(
            title="Constant",
            description="Constant description.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_CONSTANT,
            },
        )

        temp_option_remove_string_selection_enhanced: Literal["A", "B", "C"] = Field(
            title="Option",
            description="Option description.",
            default="A",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_SELECTION_ENHANCED,
                SchemaKey.DESCRIPTION_BY_KEY: {
                    "A": "Description for option A.",
                    "B": "Description for option B.",
                    "C": "Description for option C.",
                },
                SchemaKey.LATEX_BY_KEY: {
                    "A": r"A_{latex}",
                    "B": r"B_{latex}",
                    "C": r"C_{latex}",
                },
                SchemaKey.TITLE_BY_KEY: {"A": "Option A", "B": "Option B", "C": "Option C"},
            },
        )

        temp_option_remove_string_constant_enhanced: Literal["A"] = Field(
            title="Constant",
            description="Constant description.",
            json_schema_extra={
                SchemaKey.UI_ELEMENT: UIElement.STRING_CONSTANT_ENHANCED,
                SchemaKey.DESCRIPTION_BY_KEY: {
                    "A": "Description for option A.",
                },
                SchemaKey.LATEX_BY_KEY: {
                    "A": r"A_{latex}",
                },
                SchemaKey.TITLE_BY_KEY: {
                    "A": "Option A",
                },
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
    neuron_set: AllNeuronSetUnion = Field(
        title="Neuron Set",
        description="Set of neurons to be extracted from the parent circuit, including their"
        " connectivity.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_UNION,
            SchemaKey.GROUP: BlockGroup.EXTRACTION_TARGET,
            SchemaKey.GROUP_ORDER: 0,
        },
    )

    neuron_sets: dict[str, AllNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_DICTIONARY,
            SchemaKey.SINGULAR_NAME: "Neuron Set",
            SchemaKey.REFERENCE_TYPES: ALL_NEURON_SETS_REFERENCE_TYPES,
            SchemaKey.GROUP: BlockGroup.EXTRACTION_TARGET,
            SchemaKey.GROUP_ORDER: 1,
        },
    )

    entity_dependent_block_example: EntityDependentBlockExample = Field(
        title="Entity Dependent Block Example",
        description="Example block which is only usable for certain circuits based on the value of"
        " the CircuitUsability.SHOW_INPUT_RESISTANCE_BASED_STIMULI property for that circuit.",
        json_schema_extra={
            SchemaKey.UI_ELEMENT: UIElement.BLOCK_SINGLE,
            SchemaKey.GROUP: BlockGroup.EXTRACTION_TARGET,
            SchemaKey.GROUP_ORDER: 2,
        },
    )

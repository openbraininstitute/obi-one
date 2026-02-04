from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field

from obi_one.core.block import Block
from obi_one.core.info import Info
from obi_one.core.scan_config import ScanConfig
from obi_one.scientific.tasks.generate_simulation_configs import CircuitDiscriminator
from obi_one.scientific.unions.unions_neuron_sets import (
    CircuitExtractionNeuronSetUnion,
    NeuronSetReference,
    SimulationNeuronSetUnion,
)


class BlockGroup(StrEnum):
    """Block Groups."""

    SETUP = "Setup"
    EXTRACTION_TARGET = "Extraction Target"


class SchemaExampleScanConfig(ScanConfig):
    """ScanConfig for extracting sub-circuits from larger circuits."""

    single_coord_class_name: ClassVar[str] = ""
    name: ClassVar[str] = "Schema Example"
    description: ClassVar[str] = "Useful for testing and generating example schema."

    model_config = ConfigDict(
        json_schema_extra={
            "ui_enabled": True,
            "group_order": [BlockGroup.SETUP, BlockGroup.EXTRACTION_TARGET],
        }
    )

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
            json_schema_extra={
                "ui_element": "model_identifier",
            },
        )
        example_boolean_input: bool = Field(
            json_schema_extra={
                "ui_element": "boolean_input",
            },
            default=True,
            title="Include Virtual Populations",
            description="Include virtual neurons which target the cells contained in the specified"
            " neuron set (together with their connectivity onto the specified neuron set) in the"
            " extracted sub-circuit.",
        )

        temp_option_remove_string_selection: Literal["A", "B", "C"] = Field(
            json_schema_extra={
                "ui_element": "string_selection",
            },
            title="Option",
            description="Option description.",
            default="A",
        )

        temp_option_remove_string_constant: Literal["A"] = Field(
            title="Constant",
            description="Constant description.",
            json_schema_extra={
                "ui_element": "string_constant",
            },
        )

        temp_option_remove_string_selection_enhanced: Literal["A", "B", "C"] = Field(
            title="Option",
            description="Option description.",
            default="A",
            json_schema_extra={
                "ui_element": "string_selection_enhanced",
                "description_by_key": {
                    "A": "Description for option A.",
                    "B": "Description for option B.",
                    "C": "Description for option C.",
                },
                "latex_by_key": {
                    "A": r"A_{latex}",
                    "B": r"B_{latex}",
                    "C": r"C_{latex}",
                },
                "title_by_key": {"A": "Option A", "B": "Option B", "C": "Option C"},
            },
        )

        temp_option_remove_string_constant_enhanced: Literal["A"] = Field(
            title="Constant",
            description="Constant description.",
            json_schema_extra={
                "ui_element": "string_constant_enhanced",
                "description_by_key": {
                    "A": "Description for option A.",
                },
                "latex_by_key": {
                    "A": r"A_{latex}",
                },
                "title_by_key": {
                    "A": "Option A",
                },
            },
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
    neuron_set: CircuitExtractionNeuronSetUnion = Field(
        title="Neuron Set",
        description="Set of neurons to be extracted from the parent circuit, including their"
        " connectivity.",
        json_schema_extra={
            "ui_element": "block_union",
            "group": BlockGroup.EXTRACTION_TARGET,
            "group_order": 0,
        },
    )

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        default_factory=dict,
        description="Neuron sets for the simulation.",
        json_schema_extra={
            "ui_element": "block_dictionary",
            "singular_name": "Neuron Set",
            "reference_type": NeuronSetReference.__name__,
            "group": BlockGroup.EXTRACTION_TARGET,
            "group_order": 1,
        },
    )

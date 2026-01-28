from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import Field

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

    class Config:
        json_schema_extra: ClassVar[dict] = {
            "ui_enabled": True,
            "group_order": [
                BlockGroup.SETUP,
                BlockGroup.EXTRACTION_TARGET,
            ],
        }

    class Initialize(Block):
        circuit: CircuitDiscriminator | list[CircuitDiscriminator] = Field(
            ui_element="model_identifier",
            title="Circuit",
            description="Parent circuit to extract a sub-circuit from.",
        )
        example_boolean_input: bool = Field(
            ui_element="boolean_input",
            default=True,
            title="Include Virtual Populations",
            description="Include virtual neurons which target the cells contained in the specified"
            " neuron set (together with their connectivity onto the specified neuron set) in the"
            " extracted sub-circuit.",
        )

        temp_option_remove_string_selection: Literal["A", "B", "C"] = Field(
            ui_element="string_selection",
            title="Option",
            description="Option description.",
            default="A",
        )

        temp_option_remove_string_constant: Literal["A"] = Field(
            ui_element="string_constant",
            title="Constant",
            description="Constant description.",
        )

        temp_option_remove_string_selection_enhanced: Literal["A", "B", "C"] = Field(
            ui_element="string_selection_enhanced",
            title="Option",
            description="Option description.",
            default="A",
            description_by_key={
                "A": "Description for option A.",
                "B": "Description for option B.",
                "C": "Description for option C.",
            },
            latex_by_key={
                "A": r"A_{latex}",
                "B": r"B_{latex}",
                "C": r"C_{latex}",
            },
        )

        temp_option_remove_string_constant_enhanced: Literal["A"] = Field(
            ui_element="string_constant_enhanced",
            title="Constant",
            description="Constant description.",
            description_by_key={"A": "Description for option A."},
            latex_by_key={
                "A": r"A_{latex}",
            },
        )

    info: Info = Field(
        ui_element="root_block",
        title="Info",
        description="Information about the circuit extraction campaign.",
        group=BlockGroup.SETUP,
        group_order=0,
    )
    initialize: Initialize = Field(
        ui_element="root_block",
        title="Initialization",
        description="Parameters for initializing the circuit extraction campaign.",
        group=BlockGroup.SETUP,
        group_order=1,
    )
    neuron_set: CircuitExtractionNeuronSetUnion = Field(
        ui_element="block_single",
        title="Neuron Set",
        description="Set of neurons to be extracted from the parent circuit, including their"
        " connectivity.",
        group=BlockGroup.EXTRACTION_TARGET,
        group_order=0,
    )

    neuron_sets: dict[str, SimulationNeuronSetUnion] = Field(
        ui_element="block_dictionary",
        default_factory=dict,
        reference_type=NeuronSetReference.__name__,
        description="Neuron sets for the simulation.",
        singular_name="Neuron Set",
        group=BlockGroup.EXTRACTION_TARGET,
        group_order=0,
    )

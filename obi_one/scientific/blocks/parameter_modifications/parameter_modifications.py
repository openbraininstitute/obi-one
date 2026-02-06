from abc import ABC, abstractmethod
from pathlib import Path
from typing import Annotated, ClassVar, Self

from pydantic import Field, NonNegativeFloat, PositiveFloat, PrivateAttr, model_validator

from obi_one.core.block import Block
from obi_one.core.exception import OBIONEError
from obi_one.scientific.library.circuit import Circuit
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)

from obi_one.scientific.library.entity_property_types import CircuitPropertyType, EntityType



class BasicParameterModification(Block, ABC):
    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to modification is applied.",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
        },
    )

    variable_for_modification: tuple[str, str] = Field(
        title="Variable for Modification",
        description="Mechanism Variable for modification. These could include variables of ion channel models, passive properties of the cell, ...",
        min_length=1,
        json_schema_extra={
                            "ui_element": "entity_property_dropdown",
                            "entity_type": EntityType.CIRCUIT,
                            "property": CircuitPropertyType.MECHANISM_VARIABLES,
                        } 
    )

    # 

    # {"mechanism A": {"variable_1": {"original_value": 0.1, "bounds": [0, 1], "units": "mV"},
                    #  "variable_2": {"original_value": 0.2, "bounds": [0, 1], "units": "mV"}},

    new_value: float | list[float] = Field(
        default=0.1,
        title="New Value",
        description="New value to set for the parameter.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )

    def config(self, default_node_set: str) -> dict:

        if (self.neuron_set is not None) and (
            self.neuron_set.block.population_type(circuit, population) != "biophysical"
        ):
            msg = (
                f"Neuron Set '{self.neuron_set.block.block_name}' for {self.__class__.__name__}: "
                f"'{self.block_name}' should be biophysical!"
            )
            raise OBIONEError(msg)

        return self._generate_config()

        return {
            "type": self.type,
            "node_set": resolve_neuron_set_ref_to_node_set(self.neuron_set, default_node_set),
            "variable_for_modification": self.variable_for_modification,
            "new_value": self.new_value,
        }


class AdvancedParameterModification(Block, ABC):
    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to modification is applied.",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
        },
    )
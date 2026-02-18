from typing import Annotated

from pydantic import Field

from obi_one.core.base import OBIBaseModel
from obi_one.core.block import Block
from obi_one.scientific.library.emodel_parameters import _expand_section_list
from obi_one.scientific.library.entity_property_types import (
    CircuitMappedProperties,
    MappedPropertiesGroup,
)
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)


class BySectionListModification(OBIBaseModel):
    """Modification for RANGE variables by section list.

    Example:
        ion_channel_id: "abc123"
        variable_name: "gCa_HVAbar_Ca_HVA2"
        section_list_modifications: {
            "somatic": 0.1,
            "axonal": [0.1, 0.2, 0.3],
        }
    """

    ion_channel_id: Annotated[str, Field(min_length=1, description="ID of the ion channel")]
    variable_name: str = Field(
        description="Name of the RANGE variable (e.g., 'gCa_HVAbar_Ca_HVA2')"
    )
    section_list_modifications: dict[str, float | list[float]] = Field(
        default_factory=dict,
        description="Modifications per section list (e.g., {'somatic': 0.1, 'axonal': 0.2})",
    )


class ByNeuronModification(OBIBaseModel):
    """Modification for GLOBAL variables.

    Example:
        ion_channel_id: "abc123"
        channel_name: "NaTg"
        variable_name: "ena_NaTg"
        new_value: 0.5
    """

    ion_channel_id: Annotated[str, Field(min_length=1, description="ID of the ion channel")]
    channel_name: Annotated[
        str,
        Field(
            min_length=1,
            description="Channel suffix (e.g., 'NaTg') used as key in conditions.mechanisms",
        ),
    ]
    variable_name: str = Field(description="Name of the GLOBAL variable (e.g., 'ena_NaTg')")
    new_value: float | list[float] = Field(description="New value(s) for the variable")


class BySectionListNeuronalParameterModification(Block):
    """Modify RANGE variables of ion channels for specific section lists.

    This block allows modifying ion channel RANGE variables (e.g., conductances)
    with different values for different section lists (e.g., somatic, axonal).
    """

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to which modification is applied.",
        exclude=True,
        json_schema_extra={"ui_hidden": True},
    )

    modification: BySectionListModification = Field(
        title="RANGE Variable Modification",
        description="Ion channel RANGE variable modification by section list.",
        json_schema_extra={
            "ui_element": "ion_channel_range_variable_modification",
            "property_group": MappedPropertiesGroup.CIRCUIT,
            "property": CircuitMappedProperties.ION_CHANNEL_RANGE_VARIABLES,
        },
    )

    def config(self, _default_population_name: str, default_node_set: str) -> list[dict]:
        """Generate SONATA conditions.modifications entries for each section list.

        Returns:
            List of SONATA modification dicts, one per section list.
        """
        node_set = resolve_neuron_set_ref_to_node_set(self.neuron_set, default_node_set)

        modifications = []
        for section_list, value in self.modification.section_list_modifications.items():
            if section_list == "all":
                modifications.append(
                    {
                        "name": f"modify_{self.modification.variable_name}_all",
                        "node_set": node_set,
                        "type": "configure_all_sections",
                        "section_configure": f"%s.{self.modification.variable_name} = {value}",
                    }
                )
                continue

            modifications.extend(
                {
                    "name": f"modify_{self.modification.variable_name}_{expanded_section_list}",
                    "node_set": node_set,
                    "type": "section_list",
                    "section_configure": (
                        f"{expanded_section_list}.{self.modification.variable_name} = {value}"
                    ),
                }
                for expanded_section_list in _expand_section_list(section_list)
            )

        return modifications


class ByNeuronNeuronalParameterModification(Block):
    """Modify GLOBAL variables of ion channels.

    This block allows modifying ion channel GLOBAL variables that apply
    to the entire neuron (e.g., reversal potentials).
    """

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to which modification is applied.",
        exclude=True,
        json_schema_extra={"ui_hidden": True},
    )

    modification: ByNeuronModification = Field(
        title="GLOBAL Variable Modification",
        description="Ion channel GLOBAL variable modification.",
        json_schema_extra={
            "ui_element": "ion_channel_global_variable_modification",
            "property_group": MappedPropertiesGroup.CIRCUIT,
            "property": CircuitMappedProperties.ION_CHANNEL_GLOBAL_VARIABLES,
        },
    )

    def config(self, _default_population_name: str, _default_node_set: str) -> dict:
        """Generate SONATA conditions.mechanisms entry.

        Returns:
            Dict of {channel_name: {variable_name: value}} for conditions.mechanisms.
        """
        return {
            self.modification.channel_name: {
                self.modification.variable_name: self.modification.new_value
            }
        }

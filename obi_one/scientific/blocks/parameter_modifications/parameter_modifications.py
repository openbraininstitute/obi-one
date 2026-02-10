from pydantic import Field

from obi_one.core.block import Block
from obi_one.scientific.library.entity_property_types import CircuitPropertyType, EntityType
from obi_one.scientific.unions.unions_neuron_sets import (
    NeuronSetReference,
    resolve_neuron_set_ref_to_node_set,
)


class BasicParameterModification(Block):
    """Modify a single mechanism variable of the emodel."""

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to modification is applied.",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
        },
    )

    variable_for_modification: str = Field(
        title="Variable for Modification",
        description="Mechanism variable for modification (e.g. 'g_pas.all', 'decay_CaDynamics_DC0.somatic', 'TTX').",
        min_length=1,
        json_schema_extra={
            "ui_element": "entity_property_dropdown",
            "entity_type": EntityType.CIRCUIT,
            "property": CircuitPropertyType.MECHANISM_VARIABLES,
        },
    )

    new_value: float | list[float] = Field(
        default=0.1,
        title="New Value",
        description="New value to set for the parameter.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )

    def config(self, default_population_name: str, default_node_set: str) -> dict:
        """Generate a SONATA conditions.modifications entry.

        Produces one of three modification types:
        - ttx: blocks sodium channels (special TTX entry)
        - configure_all_sections: applies to all sections (section_list == "all")
        - section_list: applies to a specific NEURON SectionList

        Args:
            default_population_name: Default population name of the circuit.
            default_node_set: Default node set name.

        Returns:
            A dict representing a SONATA conditions.modifications entry.
        """
        node_set = resolve_neuron_set_ref_to_node_set(self.neuron_set, default_node_set)

        # Parse combined "neuron_variable.section_list" format
        parts = self.variable_for_modification.split(".", 1)
        neuron_variable = parts[0]
        section_list = parts[1] if len(parts) == 2 else ""

        # Special case: TTX
        if neuron_variable == "TTX":
            return {
                "name": "applyTTX",
                "node_set": node_set,
                "type": "ttx",
            }

        # configure_all_sections: applies to all sections
        if section_list == "all":
            return {
                "name": f"modify_{neuron_variable}_all",
                "node_set": node_set,
                "type": "configure_all_sections",
                "section_configure": f"%s.{neuron_variable} = {self.new_value}",
            }

        # section_list: applies to a specific section list
        return {
            "name": f"modify_{neuron_variable}_{section_list}",
            "node_set": node_set,
            "type": "section_list",
            "section_configure": f"{section_list}.{neuron_variable} = {self.new_value}",
        }


class CustomParameterModification(Block):
    """Modify an arbitrary NEURON section variable (e.g. cm, ena, ek).

    Use this for parameters not listed in the mechanism variables dropdown.
    The variable name must follow the format 'variable.sectionlist'
    (e.g. 'cm.axonal', 'ena.somatic') or just 'variable' for TTX.
    See https://sonata-extension.readthedocs.io/en/latest/sonata_simulation.html#parameters-required-for-modifications
    """

    neuron_set: NeuronSetReference | None = Field(
        default=None,
        title="Neuron Set (Target)",
        description="Neuron set to modification is applied.",
        json_schema_extra={
            "ui_element": "reference",
            "reference_type": NeuronSetReference.__name__,
        },
    )

    variable_for_modification: str = Field(
        title="Variable for Modification",
        description="NEURON variable name in 'variable.sectionlist' format (e.g. 'cm.axonal', 'ena.somatic', 'g_pas.all').",
        min_length=1,
        json_schema_extra={
            "ui_element": "string_input",
        },
    )

    new_value: float | list[float] = Field(
        default=0.1,
        title="New Value",
        description="New value to set for the parameter.",
        json_schema_extra={
            "ui_element": "float_parameter_sweep",
        },
    )

    def config(self, default_population_name: str, default_node_set: str) -> dict:
        """Generate a SONATA conditions.modifications entry.

        Produces one of three modification types:
        - ttx: blocks sodium channels (special TTX entry)
        - configure_all_sections: applies to all sections (section_list == "all")
        - section_list: applies to a specific NEURON SectionList

        Args:
            default_population_name: Default population name of the circuit.
            default_node_set: Default node set name.

        Returns:
            A dict representing a SONATA conditions.modifications entry.
        """
        node_set = resolve_neuron_set_ref_to_node_set(self.neuron_set, default_node_set)

        # Parse combined "neuron_variable.section_list" format
        parts = self.variable_for_modification.split(".", 1)
        neuron_variable = parts[0]
        section_list = parts[1] if len(parts) == 2 else ""

        # Special case: TTX
        if neuron_variable == "TTX":
            return {
                "name": "applyTTX",
                "node_set": node_set,
                "type": "ttx",
            }

        # configure_all_sections: applies to all sections
        if section_list == "all":
            return {
                "name": f"modify_{neuron_variable}_all",
                "node_set": node_set,
                "type": "configure_all_sections",
                "section_configure": f"%s.{neuron_variable} = {self.new_value}",
            }

        # section_list: applies to a specific section list
        return {
            "name": f"modify_{neuron_variable}_{section_list}",
            "node_set": node_set,
            "type": "section_list",
            "section_configure": f"{section_list}.{neuron_variable} = {self.new_value}",
        }